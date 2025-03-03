from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar
from abc import abstractmethod

import pylogfile.base as plf
import numpy as np
import json
import os
import sys

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
	''' This class is used to define a state of controls/inputs from the UI. This
	is used to track both what has been performed on datasets, and what is requested
	by the UI.
	'''
	
	def __init__(self, log):
		
		self.log = log
		
		# Dictionary of parameters controlled/monitored by the widgets
		self._parameters = {}
	
	def add_param(self, param:str, val):
		self.log.lowdebug(f"Creating >:q{param}< with initial value >:a{val}<.")
		self._parameters[param] = val
	
	def has_param(self, param:str):
		''' Checks if the specified parameter is contained in the control state.'''
		return (param in self._parameters)
	
	def get_param(self, param:str):
		return self._parameters[param]
	
	def update_param(self, param:str, val, add_if_missing:bool=False):
		
		if not self.has_param(param):
			if add_if_missing:
				self.add_param(param, val)
				return
			else:
				return
		
		self.log.lowdebug(f"Parameter >:q{param}< changed to >:a{val}<")
		self._parameters[param] = val
	
	def summarize(self):
		return f"{self._parameters}"
	
class BHWidget(QWidget):
	
	def __init__(self, main_window, dataset_changed_callback=None):
		super().__init__()
		self.main_window = main_window
		self.control_requested = main_window.control_requested
		self.data_manager = main_window.data_manager
		self.log = main_window.log
		
		# Callback function to run (if provided) when the active dataset changes
		self.dataset_changed_callback = dataset_changed_callback
	
	def _dataset_changed(self):
		''' Tells widget the dataset has changed. Called by main_window when the
		broadcast_dataset_changed() function is called. Runs a callback that
		receives a single argument - the BHWidget object. '''
		
		# Check if callback provided
		if (self.dataset_changed_callback is not None) and callable(self.dataset_changed_callback):
			self.dataset_changed_callback(self)

class BHListenerWidget(BHWidget):
	''' This class defines a widget which will automatically update to match the
	BHControlState when neccesary. It's designed to abstract the control system
	from the user, so making robust controls is simpler.'''
	
	def __init__(self, main_window, **kwargs):
		super().__init__(main_window, **kwargs)
		
		self.is_current = False
		self._is_active = True # Indicates if the widget is visible and should be updated (for tabs)
	
	def is_active(self):
		return self._is_active
	
	def set_active(self, b:bool):
		''' Sets the widget as active or inactive '''
		self._is_active = b
		self._ensure_current()
	
	def _get_update(self):
		''' Tells the plot that the control state has changed. Called by main
		 window during broadcast control changed to all control subscribers. '''
		
		# Set as non-current
		self.is_current = False
		
		# Tell it to re-render if active
		self._ensure_current()
	
	def _ensure_current(self):
		''' Tells the plot to re-render if out of date '''
		
		# Update if active and out of date
		if self.is_active() and (not self.is_current):
			self._render_widget()
	
	@abstractmethod
	def _render_widget(self):
		''' Function responsible for updating the widget to reflect the control state. 
		Automatically called by _get_update() when plot is active. '''
		pass

class BHControllerWidget(BHWidget):
	
	def __init__(self, main_window, **kwargs):
		super().__init__(main_window, **kwargs)
	
	@staticmethod
	def broadcaster(func):
		''' Decorator to make a function push all changes to the ControlState 
		to all subscriber BHListenerWidgets. '''
		
		def wrapper(self, *args, **kwargs):
			func(self, *args, **kwargs)
			self.main_window.broadcast_control_changes()
		return wrapper

class BHTabWidget(QTabWidget):
	
	def __init__(self, main_window, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		self.main_window = main_window
		self.currentChanged.connect(self.update_active_widget)
	
	def update_active_widget(self):
		
		# Get active tab
		active_idx = self.currentIndex()
		
		# Loop over all tabs
		idx = 0
		while True:
			
			# Get widget, break when out of range
			wid = self.widget(idx)
			if wid is None:
				break
			
			# Set active status
			wid.set_active(idx == active_idx)
			
			# Update index
			idx += 1
		
		self.main_window.broadcast_control_changes()

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
	
	def __init__(self, log, source_info:BHDataSource):
		
		# Describes the ControlState that has acted on the data
		self.control_performed = BHControlState(log)
		self.log = log
		self.source_info = source_info
		self.unique_id = source_info.unique_id

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
		
		# Function that will be called when the dataset changes, to broadcast to
		# all interested widgets that a change has occurred. THis function will
		# automatically be set by the MainWindow.
		self.broadcast_callback = None
	
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
	
	def set_active_dataset(self, unique_id:int, active_index:int=0):
		''' Sets the active dataset, loading it from file if required.
		'''
		
		# Look for data already loaded
		for idx, ds in enumerate(self.loaded_data):
			if ds.unique_id == unique_id:
				self.active_datasets[active_index] = idx
				self.log.info(f"Changed dataset for slot >:a{active_index}< to ID:>{unique_id}<.")
				self.broadcast_was_changed()
				return True
		
		# Else check unlaoded data
		for ulds in self.sources_info:
			# Found config
			if ulds.unique_id == unique_id:
				# Load data
				self.loaded_data.append(self.load_function(ulds, self.log))
				self.active_datasets[active_index] = len(self.loaded_data)-1
				self.log.info(f"Loaded dataset from file with unique_id >{unique_id}< for slot >:a{active_index}<")
				self.broadcast_was_changed()
				return True
		
		
		
		self.log.error(f"Failed to find dataset with unique_id {unique_id}")
		return False

	def broadcast_was_changed(self):
		if (self.broadcast_callback is not None) and callable(self.broadcast_callback):
			self.broadcast_callback()
	
	def get_active(self, active_index:int=0):
		''' Returns the active (or selected) dataset. If the end-user application 
		requires multiple simultaneously active datasets, the active_index can
		be used to select the secondary, tertiary etc datasets.
		'''
		
		# Check that set has been selected
		if active_index not in self.active_datasets:
			self.log.error(f"Cannot return dataset for slot >:a{active_index}<. No dataset has been selected yet.")
			return None
		
		return self.loaded_data[self.active_datasets[active_index]]

class BHDatasetDescriptorWidget(BHWidget):
	''' The DataManager needs to have read the config file before this is callled
	so this widget knows what fields to add.'''
	
	def __init__(self, main_window):
		super().__init__(main_window, dataset_changed_callback=self.update_descriptor)
		self.main_window.add_dataset_subscriber(self)
		
		self.label_font = QtGui.QFont()
		self.label_font.setBold(True)
		
		self.filename_lab = QLabel("Filename:")
		self.filename_lab.setFont(self.label_font)
		self.filename_val = QLabel("")
		
		self.path_lab = QLabel("Full Path:")
		self.path_lab.setFont(self.label_font)
		self.path_val = QLabel("")
		
		self.param_labels = {}
		self.param_vals = {}
		
		# Loop over expected parameters
		self.param_box = QGroupBox(f"File Parameters")
		self.pb_grid = QGridLayout()
		rownum = 0
		for param in self.data_manager.expected_file_parameters:
			
			pl = QLabel(f"{param}:")
			pl.setFont(self.label_font)
			
			pv = QLabel(f"")
			
			self.param_labels[param] = pl
			self.param_vals[param] = pv
			
			# Add to grid
			self.pb_grid.addWidget(pl, rownum, 0)
			self.pb_grid.addWidget(pv, rownum, 1)
			rownum += 1
		self.param_box.setLayout(self.pb_grid)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.filename_lab, 0, 0, 1, 2)
		self.grid.addWidget(self.filename_val, 1, 0, 1, 2)
		self.grid.addWidget(self.path_lab, 2, 0, 1, 2)
		self.grid.addWidget(self.path_lab, 3, 0, 1, 2)
		self.grid.addWidget(self.param_box, 4, 0, 1, 2)
		self.setLayout(self.grid)
	
	@staticmethod
	def update_descriptor( wid):
		
		# Get active dataset
		ds = wid.data_manager.get_active()
		
		# Update fields
		wid.filename_val.setText(ds.source_info.file_name)
		wid.path_val.setText(ds.source_info.file_fullpath)
		
		# Update each parameter in turn
		for param in wid.data_manager.expected_file_parameters:
			param_val = ds.source_info.parameters[param]
			try:
				wid.param_vals[param].setText(f"{param_val}")
			except Exception as e:
				wid.log.error(f"Failed to convert parameter to string.",detail=f"{e}")
				wid.param_vals[param].setText(f"??")

class BHDatasetSelectBasicWidget(QWidget):
	
	def __init__(self, main_window, log):
		super().__init__()
		self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
		
		self.main_window = main_window
		self.manager = main_window.data_manager
		self.log = log
		
		self.grid = QGridLayout()
		
		# Create selector widget
		self.select_widget = QListWidget()
		self.select_widget.setFixedSize(QSize(200, 100))
		self.select_widget.itemClicked.connect(self.change_file)
		
		self.hspacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
		
		# Descriptor widget
		self.descriptor_widget = BHDatasetDescriptorWidget(self.main_window)
		
		# Apply layout
		self.grid.addWidget(self.select_widget, 0, 0)
		self.grid.addItem(self.hspacer, 0, 1)
		self.grid.addWidget(self.descriptor_widget, 0, 2)
		self.setLayout(self.grid)

		self.update_list()
		
	def update_list(self):
		
		# Reset list
		self.select_widget.clear()
		
		# Add each element
		for src in self.manager.sources_info:
			self.log.lowdebug(f"Added item to select widget: {src.unique_id}")
			self.select_widget.addItem(f"{src.unique_id}")
	
	def change_file(self):
		
		filename = self.select_widget.currentItem()
		if filename is None:
			self.log.warning(f">:qBHDatasetSelectBasicWidget<.>change_file<() returned early.")
			return
		
		# Change active dataset
		id = int(filename.text())
		self.manager.set_active_dataset(id)
		
		self.main_window.broadcast_control_changes()

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
		self.data_manager.broadcast_callback = lambda: self.broadcast_dataset_changes()
		self.control_requested = BHControlState(log)
		
		self.control_subscribers = [] # List of widgets to update when changes occur to control state
		self.dataset_subscribers = [] # List of widgets to update when the dataset is changed
		
		#------------- Make GUI elements ------------------
		
		# Apply window title if specified
		if window_title is not None:
			self.setWindowTitle(window_title)
		
		# Create basic GUI parameters
		self.grid = QtWidgets.QGridLayout()
		
		# Set the central widget
		central_widget = QtWidgets.QWidget()
		central_widget.setLayout(self.grid)
		self.setCentralWidget(central_widget)
		
	def add_control_subscriber(self, widget:BHListenerWidget):
		''' Adds a controlled widget to the subscribers list. These widgets 
		will be informed when a change has been made to the control state. '''
		
		self.control_subscribers.append(widget)
	
	def broadcast_control_changes(self):
		''' Informs all subscribers that the controls have changed '''
		
		for sub in self.control_subscribers:
			sub._get_update()
	
	def add_dataset_subscriber(self, widget): # TODO Make BHWidget base class
		''' Adds a widget to the subscribers list. These widgets will be 
		informed when a change has been made to the active dataset. These 
		widgets are often controls that need to update their options to 
		reflect the new data available.'''
		
		self.dataset_subscribers.append(widget)
	
	def broadcast_dataset_changes(self):
		''' Informs all subscribers that the controls have changed.'''
		
		for sub in self.dataset_subscribers:
			sub._dataset_changed()
		
	def apply_default_layout(self):
		pass
	
	def add_basic_menu_bar(self):
		
		self.bar = self.menuBar()
		
		#----------------- File Menu ----------------
		
		self.file_menu = self.bar.addMenu("File")
		
		# self.save_graph_act = QAction("Save Graph", self)
		# self.save_graph_act.setShortcut("Ctrl+Shift+G")
		# self.file_menu.addAction(self.save_graph_act)
		
		self.close_window_act = QAction("Close Window", self)
		self.close_window_act.setShortcut("Ctrl+W")
		self.close_window_act.triggered.connect(self._basic_menu_close)
		self.file_menu.addAction(self.close_window_act)
		
		#----------------- Edit Menu ----------------
		
		self.edit_menu = self.bar.addMenu("Edit")
		
		# self.save_graph_act = QAction("Save Graph", self)
		# self.save_graph_act.setShortcut("Ctrl+Shift+G")
		# self.file_menu.addAction(self.save_graph_act)
		
		self.refresh_act = QAction("Refresh", self)
		self.refresh_act.setShortcut("Ctrl+R")
		self.refresh_act.triggered.connect(self._basic_menu_refresh)
		self.edit_menu.addAction(self.refresh_act)
		
		

	def _basic_menu_close(self):

		self.close()
		sys.exit(0)
	
	def _basic_menu_refresh(self):

		self.broadcast_control_changes()