from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar

import pylogfile.base as plf
import numpy as np
import json
import os

# from pylogfile.base import *

log = plf.LogPile()
log.set_terminal_level("DEBUG")

def apply_abbreviations(path:list, abbrevs:dict):
	''' Applies abbreviations to path.
	
	Parameters:
		path: list of strings specifying directories
		abbrevs: Dictionary s.t. The keys are the shortcuts, the values
			what will be inserted in place of the shortcut. Must match entire
			shortcuts must match an entire string in the path list.
	
	Returns:
		Path list with abbreviations replaced.
	'''
	
	new_path = []
	
	# Scan over path items
	for pd in path:
		
		# Check if abbreviation is present
		if pd in abbrevs:
			new_path.append(expand_path_list(abbrevs[pd], abbrevs))
		else:
			new_path.append(pd)
	
	return new_path

def expand_path_list(path:list, abbrevs:dict):
	''' Applies abbreviations and joins path elements.'''
	
	npath = apply_abbreviations(path, abbrevs)
	return os.path.join(*npath)

class BHControlState:
	
	def __init__(self, log):
		
		self.log = log

class BHDataSource():
	''' Class representing a data source. It only specified where to find the
	data, and parameters/conditions for the data. It does not contain
	the actual data itself.'''
	
	def __init__(self, filename:str, params:dict, valid_idx, unique_id):
		self.file_fullpath = filename
		self.file_name = os.path.basename(filename)
		self.parameters = params
		self.valid_active_set_indices = []
		
		self.unique_id = unique_id

class BHDataset():
	''' Represents the data contained in a single file or dataset. This class will
	be extended by the end user to perform calculations on the data. It will also
	contain a state machine (ControlState instance) to track what has been done
	to the data vs what was requested by the user.
	
	This class will likely need to be inherited by the end user so they can customize
	how the data is loaded.
	'''
	
	def __init__(self, log, unique_id):
		
		# Describes the ControlState that has acted on the data
		self.control_performed = BHControlState(log)
		self.log = log
		self.unique_id = unique_id

class DataFilterLayer():
	
	def __init__(self, layer_idx:int, group_parameters:list, include_all:bool=False):
		
		# This is the (0-based) count for filtering order
		self.layer_idx = layer_idx
		
		# These are the BHDataSource parameters that will be filtered in this layer. The
		# list can contain 1+ elements.
		self.group_parameters = group_parameters
		
		# Specifies if this layer should include an option to enable all filter options
		self.include_all_option = include_all

class BHDatasetManager():
	''' This class organizes multiple independent datasets represented
	by multiple files. It loads them when neccesary and keeps them in memory to
	avoid unneccesary delays.
	
	The goal is for the end user to only need to customize the Dataset class, not
	everything else.
	'''
	
	def __init__(self, log, load_function):
		self.log = log
		
		# List of parameters expected in each file config specification
		self.expected_file_parameters = []
		
		# Abbreviations from the conf file.
		self.abbrevs = {}
		
		self.loaded_data = []
		self.active_datasets = {} # Stores index (for loaded_data) of the active dataset. Key = slot #
		
		# List of dictionaries defining the various data sources specified by the
		# conf file.
		self.sources_info = []
		
		# How the data selector widget should be arranged
		self.org_structure = []
		
		# Function (written by end user) to create a dataset. Will be given a 
		# BHDataSource object and LogPile and should return a BHDataset-derived class instance.
		self.load_function = load_function
	
	def load_configuration(self, filename:str=None, filepath:list=None, user_abbrevs:dict={}):
		''' Reads a configuration file in JSON format that defines the data sources
		available.
		
		Parameters:
			filename: String filename. Optional, if not provided filepath must be provided. No abbreviations
				can be used in filename.
			filepath: List of filename and path elements. Abbreviations can be used. Optional, if not
				provided, filename must be specified.
			user_abbrevs: Optional dictionary of abbreviations. 
		
		Returns:
			True/false for successful load status.
		'''
		
		# Add user abbreviations to abbreviation list. The user_abbrevs are useful
		# for letting the end-user app find servers or external hard drives with
		# data sources, and pass that location to the BHDatasetManager on the fly,
		# while the conf file can contain just the abbreviation. Note that these
		# abbreviations will also apply to the filename. 
		for ua in user_abbrevs:
			self.abbrevs[ua] = user_abbrevs[ua]
		
		# Expand filename
		if filename is None:
			if filepath is None:
				raise Exception(f"Either filename or filepath must be specified.")
			filename = expand_path_list(filepath, user_abbrevs)
		
		# Load json file
		try:
			with open(filename, 'r') as fh:
				data_conf = json.load(fh)
		except Exception as e:
			self.log.critical(f"Failed to load BHDatasetManager configuration file.", detail=f"{e}")
			return False
		
		# Read abbreviations from file
		try:
			for ab in data_conf['dir_abbrev']:
				short = ab['shortcut']
				val = ab['expanded']
				self.abbrevs[short] = val
				self.log.lowdebug(f"Adding abbreviation from file: >:a{short}< -\> >{val}<")
		except Exception as e:
			self.log.critical(f"Failed to load BHDatasetManager configuration file >dir_abbrev< section.", detail=f"{e}")
			return False
		
		# Read data_sources
		first_iter = True
		next_unique_id = 0
		try:
			
			for idx, srcdict in enumerate(data_conf['data_sources']):
				
				# Get filename
				try:
					file = expand_path_list(srcdict['file_path'], self.abbrevs)
				except Exception as e:
					fp = srcdict['file_path']
					self.log.critical(f"Failed to load BHDatasetManager configuration file >data_sources< section.", detail=f"Exception=({e}), filepath = {fp}, abbrevs = {self.abbrevs}")
					return False
				
				# Initialize parameters
				if first_iter:
					self.expected_file_parameters = list(srcdict['parameters'].keys())
					
				# Read all parameters
				params = {}
				for efp in self.expected_file_parameters:
					
					# Check for missing parameter
					if efp not in srcdict['parameters']:
						self.log.critical(f"Parameter >{efp}< missing for data_source No. {idx} (File={file}).")
						return False
					
					params[efp] = srcdict['parameters'][efp]
				
				# Save BHDataSource
				self.log.lowdebug(f"Adding BHDataSource from file: >:a{file}<")
				self.sources_info.append( BHDataSource(file, params, srcdict['valid_active_set_indices'], next_unique_id) )
				next_unique_id += 1
				
		except Exception as e:
			self.log.critical(f"Failed to load BHDatasetManager configuration file >data_sources< section.", detail=f"{e}")
			return False
		
		# Read organizational structure
		try:
			for srcdict in data_conf['organization_structure']:
				self.org_structure.append(DataFilterLayer(srcdict['layer'], srcdict['group_parameters'], srcdict['include_all_option']))
				layer_no = srcdict['layer']
				self.log.lowdebug(f"Added organizational layer >{layer_no}< from file.")
		except Exception as e:
			self.log.critical(f"Failed to load BHDatasetManager configuration file >organization_structure< section.", detail=f"{e}")
			return False
		
		# Check that all layer numbers appear and exactly once
		for i in range(len(self.org_structure)):
			
			found = 0
			for org in self.org_structure:
				if (org.layer_idx == i):
					found += 1
			if found != 1:
				self.log.critical(f"BHDatasetManager configuration file has {found} layers at level {i}. Must be exactly 1.")
				return False
		
		return True
	
	def set_active_dataset(self, unique_id:int, dataset_slot:int=1):
		''' Sets the active dataset, loading it from file if required.
		'''
		
		# Look for data already loaded
		for idx, ds in enumerate(self.loaded_data):
			if ds.unique_id == unique_id:
				self.active_datasets[dataset_slot] = idx
				return True
		
		# Else check unlaoded data
		for ulds in self.sources_info:
			# Found config
			if ulds.unique_id == unique_id:
				# Load data
				self.loaded_data.append(self.load_function(ulds, self.log))
				self.log.info(f"Loaded dataset with unique_id >{unique_id}<.")
				return True
		
		self.log.error(f"Failed to find dataset with unique_id {unique_id}")
		return False
	
	def get_data(self, active_index:int=0):
		''' Returns the active (or selected) dataset. If the end-user application 
		requires multiple simultaneously active datasets, the active_index can
		be used to select the secondary, tertiary etc datasets.
		'''
		pass

class BHDatasetSelectBasicWidget(QWidget):
	
	def __init__(self, manager:BHDatasetManager, log):
		
		self.manager = manager
		self.log = log
		
		self.box = QGroupBox()
		self.grid = QGridLayout()
		
		self.select_widget = QListWidget()
		self.select_widget.setFixedSize(QSize(200, 100))
		self.select_widget.itemClicked.connect(self.change_file)
	
	def change_file(self):
		
		filename = self.select_widget.currentItem()
		if filename is None:
			self.log.warning(f">:qBHDatasetSelectBasicWidget<.>change_file<() returned early.")
			return
		
		# Change active dataset
		self.manager.set_active_dataset(filename=filename.text())

# class BHLayerSelectWidget(QGroupBox):
# 	''' Internal widget to BHDatasetSelectWidget. Acts as a single check box.'''
	
# 	def __init__(self, manager:BHDatasetManager, layer_parameter:str):
		
# 		self.manager = manager
# 		self.layer_parameter = layer_parameter
		
# 		# Create widget
# 		self.box = QGroupBox()
# 		self.grid = QGridLayout()
		
# 		# Create list widget
# 		self.select_widget = QListWidget()
# 		self.select_widget.setFixedSize(QSize(75, 100))
# 		# self.select_widget.itemClicked.connect(self.re) # TODO?
		
# 	def 

# class BHDatasetSelectWidget(QWidget):
# 	''' Widget that allows the user to selecet an active dataset for the BHDatasetManager object. Gets
# 	its configuration info from the BHDatasetManager itself.
# 	'''
# 	def __init__(self, manager:BHDatasetManager):
# 		super().__init__()
		
# 		self.manager = manager
		
# 		self.layer_select_widgets = []
	
# 	def build_gui(self):
# 		''' Constructs the GUI from the manager config.'''
		
# 		# Loop over org layers
# 		for layer_no in range(len(self.manager.org_structure)):
			
# 			for org in self.org_structure:
# 				if (org.layer_idx == layer_no):
					
# 					# Create widget
# 					layer_box = QGroupBox()
# 					layer_grid = QGridLayout()
					
# 					# Create list widget
# 					select_widget = BHLayerSelectWidget(self.manager)
					
# 					# Add widget to list
# 					self.layer_select_widgets.append()
	
# 	def refilter_layers(self):
		
		
	

class BHMainWindow(QtWidgets.QMainWindow):
	
	def __init__(self, log, app, data_manager, window_title:str=None):
		super().__init__()
		
		# Save basic parameters
		self.log = log
		self.app = app
		self.data_manager = data_manager
		self.control_requested = BHControlState(log)
		
		# Apply window title if specified
		if window_title is not None:
			self.setWindowTitle(window_title)
		
		# Create basic GUI parameters
		self.grid = QtWidgets.QGridLayout()
		
		# Set the central widget
		central_widget = QtWidgets.QWidget()
		central_widget.setLayout(self.grid)
		self.setCentralWidget(central_widget)
	
	def apply_default_layout(self):
		pass