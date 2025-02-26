import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT

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
	
	def __init__(self, main_window, **kwargs): #, xlabel:str="", ylabel:str="", title:str="", ):
		super().__init__(main_window, **kwargs)
		
		# Create figure in matplotlib
		self.fig1 = plt.figure()
		self.gs = self.fig1.add_gridspec(1, 1)
		self.ax1a = self.fig1.add_subplot(self.gs[0, 0])
		
		# Create Qt Figure Canvas
		self.fig_canvas = FigureCanvas(self.fig1)
		self.fig_toolbar = NavigationToolbar2QT(self.fig_canvas, self)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.fig_toolbar, 0, 0)
		self.grid.addWidget(self.fig_canvas, 1, 0)
		
		self.setLayout(self.grid)
		
		self._render_widget()
	
	def _render_widget(self):
		
		# Call custom renderer if provided
		if self.custom_render_func is not None:
			self.custom_render_func(self)
		
		self.fig1.tight_layout()
		self.fig1.canvas.draw_idle()
		
		self.is_current = True

class BHMultiPlotWidget(bh.BHListenerWidget):
	
	def __init__(self,control, grid_dim:list, plot_locations:list, custom_render_func=None): #, xlabel:str="", ylabel:str="", title:str="", ):
		super().__init__(control)
		
		# Create figure in matplotlib
		self.fig1 = plt.figure()
		self.gs = self.fig1.add_gridspec(*grid_dim)
		self.axes = []
		for ploc in plot_locations:
			self.axes.append(self.fig1.add_subplot(self.gs[ploc[0], ploc[1]]))
		
		# Create Qt Figure Canvas
		self.fig_canvas = FigureCanvas(self.fig1)
		self.fig_toolbar = NavigationToolbar2QT(self.fig_canvas, self)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.fig_toolbar, 0, 0)
		self.grid.addWidget(self.fig_canvas, 1, 0)
		
		self.custom_render_func = custom_render_func
		
		self.setLayout(self.grid)
		
		self._render_widget()
	
	def _render_widget(self):
		
		# Call custom renderer if provided
		if self.custom_render_func is not None:
			self.custom_render_func(self)
		
		self.fig1.tight_layout()
		self.fig1.canvas.draw_idle()
		
		self.is_current = True

class BHSliderWidget(bh.BHControllerWidget):
	
	def __init__(self, main_window, param, header_label:str="", initial_val:float=None, unit_label:str="", step:float=None, min:float=None, max:float=None, tick_step:float=None, dataset_changed_callback=None):
		super().__init__(main_window)
		
		# This is the parameter which the slider will control
		self.control_parameter = param
		self.unit_label = unit_label
		self.dataset_changed_callback = dataset_changed_callback #TODO: Put this into base class?
		
		# Get initial value from controls
		if initial_val is None:
			initial_val = self.main_window.control_requested.get_param(param)
		
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