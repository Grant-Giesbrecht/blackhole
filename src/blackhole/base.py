from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar

import pylogfile.base as plf
import numpy as np

# from pylogfile.base import *

log = plf.LogPile()
log.set_terminal_level("DEBUG")

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