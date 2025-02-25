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
			new_path.append(abbrevs[pd])
		else:
			new_path.append(pd)
	
	return new_path

def expand_path_list(path:list, abbrevs:dict):
	''' Applies abbreviations and joins path elements.'''
	
	npath = apply_abbreviations(path, abbrevs)
	return os.path.join(npath)

class BHControlState:
	
	def __init__(self, log):
		
		self.log = log

class BHDatasetManager():
	''' This class organizes multiple independent datasets represented
	by multiple files. It loads them when neccesary and keeps them in memory to
	avoid unneccesary delays.
	
	The goal is for the end user to only need to customize the Dataset class, not
	everything else.
	'''
	
	def __init__(self, log):
		self.log = log
		
		# List of parameters expected in each file config specification
		self.expected_file_parameters = []
		
		# Abbreviations from the conf file.
		self.abbrevs = {}
		
		# List of dictionaries defining the various data sources specified by the
		# conf file.
		self.sources_info = []
		
		# How the data selector widget should be arranged
		self.org_structure = []
	
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
				self.log.lowdebug(f"Adding abbreviation from file: {short} -> {val}")
		except Exception as e:
			self.log.critical(f"Failed to load BHDatasetManager configuration file >dir_abbrev< section.", detail=f"{e}")
			return False
		
		# # Read data_sources
		# try:
			
		# 	for srcdict in data_conf['data_sources']:
				
			
		# except Exception as e:
		# 	self.log.critical(f"Failed to load BHDatasetManager configuration file >data_sources< section.", detail=f"{e}")
		
		# # Evaluate each sweep source
		# for dss in self.data_conf['sweep_sources']:
			
		# 	#For each entry, evaluate wildcards and find actual path
		# 	full_path = get_general_path(dss['path'], dos_id_folder=True, print_details=cli_args.autopathdetails)
			
		# 	# Write log
		# 	name = dss['chip_name']
		# 	track = dss['track']
		# 	if full_path is None:
		# 		self.log.error(f"Failed to find sweep data source for chip {name}, track {track}.")
		# 	else:
		# 		self.log.debug(f"Sweep data source identified for chip {name}, track {track}.", detail=f"Path = {full_path}")
			
		# 	# Save full path string, or None for error
		# 	dss['full_path'] = full_path
		
		# # Evaluate each sparam source
		# for dss in self.data_conf['sparam_sources']:
			
		# 	#For each entry, evaluate wildcards and find actual path
		# 	cryo_full_path = get_general_path(dss['cryostat_file'], dos_id_folder=True, print_details=cli_args.autopathdetails)
			
		# 	# Write log
		# 	name = dss['chip_name']
		# 	track = dss['track']
		# 	if cryo_full_path is None:
		# 		self.log.error(f"Failed to find s-parameter data source for chip {name}, track {track}.")
		# 	else:
		# 		self.log.debug(f"S-parameter data source identified for chip {name}, track {track}.", detail=f"Path = {full_path}")
			
		# 	# Save full path string, or None for error
		# 	dss['cryo_full_path'] = cryo_full_path
		
		return True
	
	def get_data(self, active_index:int=0):
		''' Returns the active (or selected) dataset. If the end-user application 
		requires multiple simultaneously active datasets, the active_index can
		be used to select the secondary, tertiary etc datasets.
		'''
		pass

class BHDataset():
	''' Represents the data contained in a single file or dataset. This class will
	be extended by the end user to perform calculations on the data. It will also
	contain a state machine (ControlState instance) to track what has been done
	to the data vs what was requested by the user.
	
	This class will likely need to be inherited by the end user so they can customize
	how the data is loaded.
	'''
	
	def __init__(self, log):
		
		# Describes the ControlState that has acted on the data
		self.control_performed = BHControlState(log)
		self.log = log

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