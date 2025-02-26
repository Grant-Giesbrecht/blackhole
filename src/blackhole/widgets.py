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
	
	X_AUTO = "AXIS_XLIM_AUTO"
	X_MIN = "AXIS_XLIM_MIN"
	X_MAX = "AXIS_XLIM_MAX"
	Y_AUTO = "AXIS_YLIM_AUTO"
	Y_MIN = "AXIS_YLIM_MIN"
	Y_MAX = "AXIS_YLIM_MAX"
	
	def __init__(self,main_window, grid_dim:list, plot_locations:list, custom_render_func=None, include_settings_button:bool=False): #, xlabel:str="", ylabel:str="", title:str="", ):
		super().__init__(main_window)
		
		self.main_window = main_window
		
		#NOTE: The idea is that the main window will have a *global* BHControlState
		# that all widgets will ahve acceess too. If you want two unrelated widgets
		# to talk to eachother, use the global one.
		#
		# If you know the controls/inputs in question are going to be localized to a single widget
		# you can make a local control_state. The primary advantage of this is keeping the global
		# controlstate cleaner and easier to understand. 
		self.local_controls = bh.BHControlState(self.main_window.log)
		
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
		self.grid.addWidget(self.fig_toolbar, 0, 0, 1, 1)
		self.grid.addWidget(self.fig_canvas, 1, 0, 1, 2)
		
		if include_settings_button:
			self.settings_btn = QPushButton("Plot Settings", parent=self)
			self.settings_btn.setFixedSize(100, 25)
			self.settings_btn.clicked.connect(self.launch_settings_ui)
			self.grid.addWidget(self.settings_btn, 0, 1, 1, 1)
		
		self.custom_render_func = custom_render_func
		
		self.setLayout(self.grid)
		
		self._render_widget()
	
	def configure_integrated_bounds(self, ax:int=0, xlim:list=None, ylim:list=None):
		''' Configures the integrated bounds system. The bounds are stored in the local_controls 
		object, which can be tuned with a popup GUI. Must be called individually for each axis. The
		end user must place a call to apply_integrated_plot_bounds() in their custom render function
		for the bounds to be applied. 
		
		Parameters:
			ax (int): Axis number to configure
			xlim (list): List of lower and upper bound for x axis. Set to None for auto.
			ylim (list): List of lower and upper bound for y axis. Set to None for auto.
		
		Returns:
			None
		'''
		
		# Verify requested axis exists
		if ax > len(self.axes)-1:
			raise Exception(f"Axis index out of bounds.")
		
		# Configure x-axis limits
		self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.X_AUTO}", (xlim is None))
		if xlim is None:
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.X_MIN}", 0)
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.X_MAX}", 1)
		else:
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.X_MIN}", xlim[0])
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.X_MAX}", xlim[1])
		
		# Configure y-axis limits
		self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.Y_AUTO}", (ylim is None))
		if ylim is None:
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.Y_MIN}", 0)
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.Y_MAX}", 1)
		else:
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.Y_MIN}", ylim[0])
			self.local_controls.add_param(f"{ax}{BHMultiPlotWidget.Y_MAX}", ylim[1])
	
	def _render_widget(self):
		
		# Call custom renderer if provided
		if self.custom_render_func is not None:
			self.custom_render_func(self)
		
		self.fig1.tight_layout()
		self.fig1.canvas.draw_idle()
		
		self.is_current = True
	
	def apply_integrated_plot_bounds(self):
		''' End-users can place a call to this function in their render callback function. This
		will automatically set the bounds on each axis according to the values in the local control
		object. This object in turn can be tuned using a GUI if the include_settings_button option 
		is on. Cannot have > 999 axes.'''
		
		for ax in range(len(self.axes)):
			if self.local_controls.has_param(f"{ax}{BHMultiPlotWidget.X_AUTO}"):
				try:
					xauto = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.X_AUTO}")
					xmin = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.X_MIN}")
					xmax = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.X_MAX}")
					yauto = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.Y_AUTO}")
					ymin = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.Y_MIN}")
					ymax = self.local_controls.get_param(f"{ax}{BHMultiPlotWidget.Y_MAX}")
					
					# Apply X bounds
					if xauto:
						self.axes[ax].autoscale(axis='x')
					else:
						self.axes[ax].set_xlim([xmin, xmax])
					
					# Apply y bounds
					if yauto:
						self.axes[ax].autoscale(axis='y')
					else:
						self.axes[ax].set_ylim([ymin, ymax])
					
				except Exception as e:
					self.main_window.log.error(f"Cannot use integrated bounds. Missing control parameters.", detail=f"{e}")
					return

	def launch_settings_ui(self):
		
		self.settings_dialog = BHIntegratedBoundsControlWindow(self)
		self.settings_dialog.show()

class AxesConfigWidget(QWidget):
	''' Used inside BHIntegratedBoundsControlWindow to represent one tab page.'''
	
	def __init__(self, mp_widget, ax_idx:int):
		super().__init__()
		
		self.ax_idx = ax_idx
		self.mp_widget = mp_widget
		self.control = mp_widget.local_controls
		
		xauto = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.X_AUTO}")
		xmin = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.X_MIN}")
		xmax = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.X_MAX}")
		
		yauto = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.Y_AUTO}")
		ymin = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.Y_MIN}")
		ymax = self.control.get_param(f"{ax_idx}{BHMultiPlotWidget.Y_MAX}")
		
		self.xauto_cb = QCheckBox("Auto X-Limits")
		self.xauto_cb.setChecked(xauto)
		self.xauto_cb.stateChanged.connect(self.apply_changes)
		
		self.xmin_label = QLabel("X-Limit, Low:")
		self.xmin_edit = QLineEdit()
		self.xmin_edit.setValidator(QDoubleValidator())
		self.xmin_edit.setText(f"{xmin}")
		self.xmin_edit.setFixedWidth(40)
		self.xmin_edit.editingFinished.connect(self.apply_changes)
		
		self.xmax_label = QLabel("X-Limit, High:")
		self.xmax_edit = QLineEdit()
		self.xmax_edit.setValidator(QDoubleValidator())
		self.xmax_edit.setText(f"{xmax}")
		self.xmax_edit.setFixedWidth(40)
		self.xmax_edit.editingFinished.connect(self.apply_changes)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.xauto_cb, 0, 1)
		self.grid.addWidget(self.xmin_label, 1, 0)
		self.grid.addWidget(self.xmin_edit, 1, 1)
		self.grid.addWidget(self.xmax_label, 2, 0)
		self.grid.addWidget(self.xmax_edit, 2, 1)
		
		self.setLayout(self.grid)
	
	def apply_changes(self):
		
		# Read values from UI
		xauto = self.xauto_cb.isChecked()
		xmin = float(self.xmin_edit.text())
		xmax = float(self.xmax_edit.text())
		
		# Save values to controller
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_AUTO}", xauto)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_MIN}", xmin)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_MAX}", xmax)
		


class BHIntegratedBoundsControlWindow(QMainWindow):
	
	def __init__(self, mp_widget:BHMultiPlotWidget):
		super().__init__()
		
		self.mp_widget = mp_widget
		self.grid = QGridLayout()
		
		# Create tabs
		self.tab_bar = QTabWidget()
		for ax in range(len(self.mp_widget.axes)):
			self.tab_bar.addTab(AxesConfigWidget(mp_widget, ax), f"Axis {ax}")
			
		# Define grid
		self.grid.addWidget(self.tab_bar, 0, 0)
		
		self.cw = QtWidgets.QWidget()
		self.cw.setLayout(self.grid)
		self.setCentralWidget(self.cw)
		
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