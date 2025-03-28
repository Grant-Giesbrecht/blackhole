#!/usr/bin/env python

import sys
import importlib.util
import os
from colorama import Fore, Style
from pylogfile.base import *
import argparse
from itertools import groupby, count, filterfalse
import dataclasses
import json

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar

import pylogfile.base as plf
import blackhole.widgets as bhw
import blackhole.base as bh

##================================================================
# Read commandline Arguments

# if __name__ == "__main__":
parser = argparse.ArgumentParser()
parser.add_argument('filename')
parser.add_argument('--loglevel', help="Set the logging display level.", choices=['LOWDEBUG', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], type=str.upper)
parser.add_argument('-d', '--detail', help="Show log details.", action='store_true')
parser.add_argument('-a', '--afunc', help="Specify name of the analysis function.", default="analyze")
parser.add_argument('-p', '--pfunc', help="Specify name of the main/plotting function.", default="main")
args = parser.parse_args()

# Initialize log
log = plf.LogPile()
if args.loglevel is not None:
	print(f"\tSetting log level to {args.loglevel}")
	log.set_terminal_level(args.loglevel)
else:
	log.set_terminal_level("DEBUG")
log.str_format.show_detail = args.detail

def import_function_from_path(file_path, function_name):
	"""
	Imports a function from a file path provided as a string. Thanks Gemini!

	Args:
		file_path (str): The path to the Python file.
		function_name (str): The name of the function to import.

	Returns:
		function: The imported function, or None if an error occurs.
	"""
	
	if not os.path.exists(file_path):
		print(f"Error: File not found at {file_path}")
		return None

	spec = importlib.util.spec_from_file_location("module.name", file_path)
	if spec is None:
		print(f"Error: Could not create module specification for {file_path}")
		return None
	
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	try:
		function = getattr(module, function_name)
		return function
	except AttributeError:
		print(f"Error: Function '{function_name}' not found in {file_path}")
		return None

class PioneerMainWindow(bh.BHMainWindow):
	
	def __init__(self, log, app, data_manager, plot_fn:callable, analysis_fn:callable):
		super().__init__(log, app, data_manager, window_title="Black Hole: Pioneer")
		
		self.setMinimumSize(500, 500)
		
		self.analyzer_widget = bhw.FileAnalyzerWidget(self, plot_fn, analysis_fn)
		
		# Make grid
		self.main_grid = QGridLayout()
		self.main_grid.addWidget(self.analyzer_widget, 0, 0)
		
		# Create central widget
		self.central_widget = QtWidgets.QWidget()
		self.central_widget.setLayout(self.main_grid)
		self.setCentralWidget(self.central_widget)
		
		self.add_basic_menu_bar()
		
		self.show()

def main():
	
	analysis_fn = import_function_from_path(args.filename, args.afunc)
	plot_fn = import_function_from_path(args.filename, args.pfunc)

	if plot_fn is None:
		print(f"Error: Failed to retrieve function >{args.pfunc}< from specified file, >{args.filename}<.")
		sys.exit()
	if analysis_fn is None:
		print(f"Warning: No analysis function >{args.afunc}< detected in specified file, >{args.filename}<. Skipping.")
		

	# Create app object
	app = QtWidgets.QApplication(sys.argv)
	app.setStyle(f"Fusion")
	# app.setWindowIcon

	def void_fn():
		pass
	
	# Create Data Manager - it won't be used
	data_manager = bh.BHDatasetManager(log, load_function=void_fn)

	window = PioneerMainWindow(log, app, data_manager, plot_fn, analysis_fn)

	app.exec()
