from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar
from abc import abstractmethod
import pylogfile.base as plf
import numpy as np
import json
import os

import blackhole.base as bh

class BHPlotWidget(bh.BHListenerWidget):
	
	def __init__(self, control):
		super().__init__(control)
	
	def _render_widget(self):
		print(f"Control State: {self.control_requested.summarize()}")

class BHSliderWidget(bh.BHControllerWidget):
	
	def __init__(self, main_window, param, header_label:str="", initial_val:float=0, unit_label:str="", step:float=None, min:float=None, max:float=None, tick_step:float=None):
		super().__init__(main_window)
		
		# This is the parameter which the slider will control
		self.control_parameter = param
		self.unit_label = unit_label
		
		val0 = initial_val
		
		self.grid = QGridLayout()
		
		# Create header label
		self.header_label = QtWidgets.QLabel()
		self.header_label.setText(header_label)
		
		# Create slider
		self.slider = QSlider(Qt.Orientation.Vertical)
		if step is not None:
			self.slider.setSingleStep(step)
		if min is not None:
			if val0 < min:
				val0 = min
			self.slider.setMinimum(min)
		if max is not None:
			if val0 > max:
				val0 = max
			self.slider.setMaximum(max)
		if tick_step is not None:
			self.slider.setTickInterval(tick_step)
		
		# Initialize value label
		self.value_label = QtWidgets.QLabel()
		self._update_val_label(val0)
		
		# Set initial position and callback
		self.slider.setSliderPosition(val0)
		self.slider.valueChanged.connect(self.update)
		
		# Add widgets to grid
		self.grid.addWidget(self.header_label, 0, 0)
		self.grid.addWidget(self.slider, 1, 0)
		self.grid.addWidget(self.value_label, 2, 0)
	
		# Set layout
		self.setLayout(self.grid)
		
	def _update_val_label(self, value):
		
		if len(self.unit_label) > 0:
			self.value_label.setText(f"{value} ({self.unit_label})")
		else:
			self.value_label.setText(f"{value}")
	
	@bh.BHControllerWidget.broadcaster
	def update(self, new_slider_pos):
		''' Called when slider changes.'''
		
		self._update_val_label(new_slider_pos)
		self.main_window.control_requested.update_param(self.control_parameter, new_slider_pos)
		# self.main_window.broadcast_control_changes()