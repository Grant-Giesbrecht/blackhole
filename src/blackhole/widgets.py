import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize, QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar
from abc import abstractmethod
import pylogfile.base as plf
import numpy as np
import json
import os
import mplcursors

import blackhole.base as bh

def plot_pos_to_string(x):
	if isinstance(x[0], slice):
		a = x[0].start
		b = x[0].stop
		out = f"[{a}:{b}, "
	else:
		a = x[0]
		out = f"[{a}, "
	
	if isinstance(x[1], slice):
		a = x[1].start
		b = x[1].stop
		out = out + f"{a}:{b}]"
	else:
		a = x[1]
		out = out + f"{a}]"
	
	return out

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
	''' A widget that allows multiple graphs to be displayed.
	
	Features:
	 - Is a Listener widget - will automatically update when the global control state changes.
	 - Automatically includes GUI for changing graph settings.
	 - Plotting logic done via custom function, no need to make a new class.
	'''
	
	X_AUTO = "AXIS_XLIM_AUTO"
	X_MIN = "AXIS_XLIM_MIN"
	X_MAX = "AXIS_XLIM_MAX"
	Y_AUTO = "AXIS_YLIM_AUTO"
	Y_MIN = "AXIS_YLIM_MIN"
	Y_MAX = "AXIS_YLIM_MAX"
	
	def __init__(self,main_window, grid_dim:list, plot_locations:list, custom_render_func=None, include_settings_button:bool=True, enable_cursors:bool=True): #, xlabel:str="", ylabel:str="", title:str="", ):
		super().__init__(main_window)
		
		self.main_window = main_window
		
		self.enable_cursors = enable_cursors
		
		#NOTE: The idea is that the main window will have a *global* BHControlState
		# that all widgets will ahve acceess too. If you want two unrelated widgets
		# to talk to eachother, use the global one.
		#
		# If you know the controls/inputs in question are going to be localized to a single widget
		# you can make a local control_state. The primary advantage of this is keeping the global
		# controlstate cleaner and easier to understand. 
		self.local_controls = bh.BHControlState(self.main_window.log)
		
		# Save plot locations so I can later translate axis index to position (for the end user's reference)
		self.plot_locations = plot_locations
		
		# Create figure in matplotlib
		self.fig1 = plt.figure()
		self.gs = self.fig1.add_gridspec(*grid_dim)
		self.axes = []
		for idx, ploc in enumerate(plot_locations):
			self.axes.append(self.fig1.add_subplot(self.gs[ploc[0], ploc[1]]))
			self.configure_integrated_bounds(ax=idx, xlim=None, ylim=None)
		
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
		self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.X_AUTO}", (xlim is None), add_if_missing=True)
		if xlim is None:
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.X_MIN}", 0, add_if_missing=True)
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.X_MAX}", 1, add_if_missing=True)
		else:
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.X_MIN}", xlim[0], add_if_missing=True)
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.X_MAX}", xlim[1], add_if_missing=True)
		
		# Configure y-axis limits
		self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.Y_AUTO}", (ylim is None), add_if_missing=True)
		if ylim is None:
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.Y_MIN}", 0, add_if_missing=True)
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.Y_MAX}", 1, add_if_missing=True)
		else:
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.Y_MIN}", ylim[0], add_if_missing=True)
			self.local_controls.update_param(f"{ax}{BHMultiPlotWidget.Y_MAX}", ylim[1], add_if_missing=True)
	
	def _render_widget(self):
		
		# Call custom renderer if provided
		if self.custom_render_func is not None:
			self.custom_render_func(self)
		
		# Apply integrated bounds system
		self.apply_integrated_plot_bounds()
		
		# Apply tight bounds and draw
		self.fig1.tight_layout()
		self.fig1.canvas.draw_idle()
		
		# Apply cursors
		if self.enable_cursors:
			
			# Scan over axes
			for ax in self.fig1.axes:
				# Scan over lines
				for ll in ax.lines:
					mplcursors.cursor(ll, multiple=True, highlight=False)
		
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
		
		label_font = QtGui.QFont()
		label_font.setBold(True)
		
		#==================== Create Controls =================
		
		self.xauto_cb = QCheckBox("Auto X-Limits")
		self.xauto_cb.setChecked(xauto)
		self.xauto_cb.stateChanged.connect(self.apply_changes)
		
		self.xmin_label = QLabel("X-Limit, Low:")
		self.xmin_edit = QLineEdit()
		self.xmin_edit.setValidator(QDoubleValidator())
		self.xmin_edit.setText(f"{xmin}")
		self.xmin_edit.setFixedWidth(80)
		self.xmin_edit.editingFinished.connect(self.apply_changes)
		
		self.xmax_label = QLabel("X-Limit, High:")
		self.xmax_edit = QLineEdit()
		self.xmax_edit.setValidator(QDoubleValidator())
		self.xmax_edit.setText(f"{xmax}")
		self.xmax_edit.setFixedWidth(80)
		self.xmax_edit.editingFinished.connect(self.apply_changes)
		
		self.yauto_cb = QCheckBox("Auto Y-Limits")
		self.yauto_cb.setChecked(yauto)
		self.yauto_cb.stateChanged.connect(self.apply_changes)
		
		self.ymin_label = QLabel("Y-Limit, Low:")
		self.ymin_edit = QLineEdit()
		self.ymin_edit.setValidator(QDoubleValidator())
		self.ymin_edit.setText(f"{ymin}")
		self.ymin_edit.setFixedWidth(80)
		self.ymin_edit.editingFinished.connect(self.apply_changes)
		
		self.ymax_label = QLabel("Y-Limit, High:")
		self.ymax_edit = QLineEdit()
		self.ymax_edit.setValidator(QDoubleValidator())
		self.ymax_edit.setText(f"{ymax}")
		self.ymax_edit.setFixedWidth(80)
		self.ymax_edit.editingFinished.connect(self.apply_changes)
		
		#==================== Create Labels ======================
		
		ax_obj = mp_widget.axes[ax_idx]
		self.info_title_lab = QLabel("Title:")
		self.info_title_lab.setFont(label_font)
		self.info_title_labval = QLabel(f"{ax_obj.get_title()}")
		
		self.info_ylab_lab = QLabel("X Label:")
		self.info_ylab_lab.setFont(label_font)
		self.info_ylab_labval = QLabel(f"{ax_obj.get_xlabel()}")
		
		self.info_xlab_lab = QLabel("Y Label:")
		self.info_xlab_lab.setFont(label_font)
		self.info_xlab_labval = QLabel(f"{ax_obj.get_ylabel()}")
		
		self.info_pos_lab = QLabel("Position:")
		self.info_pos_lab.setFont(label_font)
		self.info_pos_labval = QLabel( plot_pos_to_string(mp_widget.plot_locations[ax_idx]) )
		
		#================ Apply to Grid ===================
		
		n1 = 0
		n2 = n1+3
		n3 = n1+n2+3
		
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.xauto_cb, n1+0, 1)
		self.grid.addWidget(self.xmin_label, n1+1, 0)
		self.grid.addWidget(self.xmin_edit, n1+1, 1)
		self.grid.addWidget(self.xmax_label, n1+2, 0)
		self.grid.addWidget(self.xmax_edit, n1+2, 1)
		
		self.grid.addWidget(self.yauto_cb, n2+0, 1)
		self.grid.addWidget(self.ymin_label, n2+1, 0)
		self.grid.addWidget(self.ymin_edit, n2+1, 1)
		self.grid.addWidget(self.ymax_label, n2+2, 0)
		self.grid.addWidget(self.ymax_edit, n2+2, 1)
		
		self.grid.addWidget(self.info_title_lab, n3+0, 0)
		self.grid.addWidget(self.info_title_labval, n3+0, 1)
		self.grid.addWidget(self.info_xlab_lab, n3+1, 0)
		self.grid.addWidget(self.info_xlab_labval, n3+1, 1)
		self.grid.addWidget(self.info_ylab_lab, n3+2, 0)
		self.grid.addWidget(self.info_ylab_labval, n3+2, 1)
		self.grid.addWidget(self.info_pos_lab, n3+3, 0)
		self.grid.addWidget(self.info_pos_labval, n3+3, 1)
		
		self.setLayout(self.grid)
	
	def apply_changes(self):
		
		# Read values from UI
		xauto = self.xauto_cb.isChecked()
		xmin = float(self.xmin_edit.text())
		xmax = float(self.xmax_edit.text())
		
		yauto = self.yauto_cb.isChecked()
		ymin = float(self.ymin_edit.text())
		ymax = float(self.ymax_edit.text())
		
		# Save values to controller
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_AUTO}", xauto)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_MIN}", xmin)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.X_MAX}", xmax)
		
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.Y_AUTO}", yauto)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.Y_MIN}", ymin)
		self.control.update_param(f"{self.ax_idx}{BHMultiPlotWidget.Y_MAX}", ymax)
		
		self.mp_widget._render_widget()

class BHIntegratedBoundsControlWindow(QMainWindow):
	
	def __init__(self, mp_widget:BHMultiPlotWidget):
		super().__init__()
		
		self.setWindowTitle("Plot Settings")
		self.setFixedSize(325, 325)
		
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
	
	def __init__(self, main_window, param, header_label:str="", initial_val:float=None, unit_label:str="", min:float=None, max:float=None, tick_step:float=1, dataset_changed_callback=None, step:float=1, editable_val_labels:bool=True, draw_labels=True):
		super().__init__(main_window)
		self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
		
		# This is the parameter which the slider will control
		self.control_parameter = param
		self.unit_label = unit_label
		self.dataset_changed_callback = dataset_changed_callback #TODO: Put this into base class?
		self.editable_val_labels = editable_val_labels
		self._manual_entry_freeze = True # Temporarily ignores changes to manuel edit box (to avoid inf cycle)
		self._slider_freeze = False # Temporarily ignores changes to slider position
		self.draw_labels = draw_labels # Controls if # labels are placed on side of slider
		# self.max_labels = 2 # Max number of side labels to add
		
		self.step_size = step
		self.scaled_min = None
		self.scaled_max = None
		
		self.side_labels = [] # List of label objects on side of slider
		
		# Get initial value from controls
		if initial_val is None:
			initial_val = self.main_window.control_requested.get_param(param)
		
		val0 = initial_val
		
		self.grid = QGridLayout()
		
		# Create header label
		self.header_label = QtWidgets.QLabel()
		self.header_label.setText(header_label)
		self.header_label_txt = header_label
		
		# self.slider.setTick(step)
		
		# Create slider
		self.slider = QSlider(Qt.Orientation.Vertical)
			
		# Step size must be an int
		self.slider.setSingleStep(1)
		
		# Adjust bounds to scale step to 1 (step must be an int)
		if min is not None:
			self.scaled_min = round(min/self.step_size)
			if val0 < min:
				val0 = min
			self.slider.setMinimum(self.scaled_min)
		if max is not None:
			self.scaled_max = round(max/self.step_size)
			if val0 > max:
				val0 = max
			self.slider.setMaximum(self.scaled_max)
		
		if tick_step is not None:
			self.slider.setTickInterval(round(tick_step/self.step_size))
		
		# Initialize value edit (if requested)
		if self.editable_val_labels:
			self.value_edit = QtWidgets.QLineEdit()
			self.value_edit.setValidator(QDoubleValidator())
			self.value_edit.setFixedWidth(50)
			self.value_edit.editingFinished.connect(self._update_from_typed_val)
		
		# Create value label
		self.value_label = QtWidgets.QLabel()
		self._update_val_label(val0)
		
		# Re-enable manual entry box
		self._manual_entry_freeze = False
		
		# Set initial position and callback
		self.set_slider_position(val0)
		self.slider.valueChanged.connect(self.update)
		
		# Add slider labels if asked
		if self.draw_labels:
			
			# TODO: Hard coded for just 2
			self.side_labels.append(QLabel(f"{self.scaled_max*self.step_size}"))
			self.side_labels.append(QLabel(f"{self.scaled_min*self.step_size}"))
			vspacer = QSpacerItem(10, 10, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
			
			self.gbl = QGroupBox()
			self.gbl_lay = QGridLayout()
			self.gbl.setStyleSheet("QGroupBox{border:0;}")
			self.gbl_lay.addWidget(self.side_labels[0], 0, 1)
			self.gbl_lay.addItem(vspacer, 1, 1)
			self.gbl_lay.addWidget(self.side_labels[1], 2, 1)
			self.gbl_lay.addWidget(self.slider, 0, 0, 3, 1)
			self.gbl.setLayout(self.gbl_lay)
			
			self.grid.addWidget(self.gbl, 1, 0)
		else:
			self.grid.addWidget(self.slider, 1, 0)
			
		# Add widgets to grid
		self.grid.addWidget(self.header_label, 0, 0)
		if self.editable_val_labels:
			self.gb = QGroupBox()
			self.gb_lay = QGridLayout()
			self.gb.setStyleSheet("QGroupBox{border:0;}")
			self.gb_lay.addWidget(self.value_edit, 0, 0)
			self.gb_lay.addWidget(self.value_label, 0, 1)
			self.gb.setLayout(self.gb_lay)
			self.grid.addWidget(self.gb, 2, 0)
			
		else:
			self.grid.addWidget(self.value_label, 2, 0)
	
		# Set layout
		self.setLayout(self.grid)
	
	def get_maximum(self):
		return self.scaled_max*self.step_size
	
	def get_minimum(self):
		return self.scaled_min*self.step_size
	
	def get_step(self):
		return self.step_size
	
	def set_maximum(self, max:float):
		''' Updates the slider's maximum value'''
		self.scaled_max = round(max/self.step_size)
		self.slider.setMaximum(self.scaled_max)
		
		# Update max label
		if self.draw_labels:
			self.side_labels[0].setText(f"{self.scaled_max*self.step_size}")
	
	def set_minimum(self, min:float):
		''' Updates the slider's minimum value'''
		self.scaled_min = round(min/self.step_size)
		self.slider.setMinimum(self.scaled_min)
		
		# Update min label
		if self.draw_labels:
			self.side_labels[1].setText(f"{self.scaled_min*self.step_size}")
	
	def set_step(self, step_size:float):
		
		# Get actual bounds
		min_val = self.scaled_min*self.step_size
		max_val = self.scaled_max*self.step_size
		slider_val = self.get_slider_position()
		
		# Change step size (scaling coefficient)
		self.step_size = step_size
		
		# Rescale bounds
		self.scaled_min = round(min_val/self.step_size)
		self.scaled_max = round(max_val/self.step_size)
		
		# Readjust slider bounds
		self.slider.setMinimum(self.scaled_min)
		self.slider.setMaximum(self.scaled_max)
		
		# Reposition slider
		self._slider_freeze = True
		self.set_slider_position(slider_val)
		self._slider_freeze = False
	
	def _update_from_typed_val(self):
		''' Update slider value after a value is entered into the text edit box'''
		
		# Abort if told to ignore changes to text edit
		if self._manual_entry_freeze:
			return
		
		# Get entered value
		val = float(self.value_edit.text())
		val_idx = round(val/self.step_size)
		if val_idx > self.scaled_max:
			val_idx = self.scaled_max
		elif val_idx < self.scaled_min:
			val_idx = self.scaled_min
		val_rd = val_idx*self.step_size
		
		# self.log.lowdebug(f"Slider entry box set to {val}, scales to {val_idx}, rounds to {val_rd}")
		
		# Apply rounded value to slider (Slider will update value with ControlState object)
		self.set_slider_position(val_rd)
		
		# Update slider to rounded value
		self._manual_entry_freeze = True # Prevent this function from running again
		self.value_edit.setText(f"{val_rd}")
		self._manual_entry_freeze = False # RE-enable this function
	
	def set_slider_position(self, val:float):
		self.log.debug(f"Setting slider position to >{val}<, index={round(val/self.step_size)}")
		self.slider.setSliderPosition(round(val/self.step_size))
	
	def get_slider_position(self):
		spos = self.slider.sliderPosition()
		return spos*self.step_size
	
	def _update_val_label(self, value):
		if self.editable_val_labels:
			if len(self.unit_label) > 0:
				self.value_label.setText(f"({self.unit_label})")
			else:
				self.value_label.setText(f"")
			self._manual_entry_freeze = True
			self.value_edit.setText(f"{value}")
			self._manual_entry_freeze = False
		else:
			if len(self.unit_label) > 0:
				self.value_label.setText(f"{value} ({self.unit_label})")
			else:
				self.value_label.setText(f"{value}")
	
	@bh.BHControllerWidget.broadcaster
	def update(self, new_slider_pos):
		''' Called when slider changes.'''
		
		# Return if slider frozen
		if self._slider_freeze:
			return
		
		self.log.debug(f"Slider moved; updating. New position: index={new_slider_pos}, val={new_slider_pos*self.step_size}")
		
		self._update_val_label(new_slider_pos*self.step_size)
		self.main_window.control_requested.update_param(self.control_parameter, new_slider_pos*self.step_size)
		# self.main_window.broadcast_control_changes()

class SliderSettingsWidget(QWidget):
	''' Used inside BHIntegratedSliderSettingsWindow to represent one tab page.'''
	
	def __init__(self, sldr_widget):
		super().__init__()
		
		# self.ax_idx = ax_idx
		self.sldr_widget = sldr_widget
		# self.control = mp_widget.local_controls
		
		xstep = self.sldr_widget.get_step()
		xmin = self.sldr_widget.get_minimum()
		xmax = self.sldr_widget.get_maximum()
		
		label_font = QtGui.QFont()
		label_font.setBold(True)
		
		#==================== Create Controls =================
		
		self.xmin_label = QLabel("Lower limit:")
		self.xmin_edit = QLineEdit()
		self.xmin_edit.setValidator(QDoubleValidator())
		self.xmin_edit.setText(f"{xmin}")
		self.xmin_edit.setFixedWidth(40)
		self.xmin_edit.editingFinished.connect(self.apply_changes)
		
		self.xmax_label = QLabel("Upper limit:")
		self.xmax_edit = QLineEdit()
		self.xmax_edit.setValidator(QDoubleValidator())
		self.xmax_edit.setText(f"{xmax}")
		self.xmax_edit.setFixedWidth(40)
		self.xmax_edit.editingFinished.connect(self.apply_changes)
		
		self.xstep_label = QLabel("Step size:")
		self.xstep_edit = QLineEdit()
		self.xstep_edit.setValidator(QDoubleValidator())
		self.xstep_edit.setText(f"{xstep}")
		self.xstep_edit.setFixedWidth(40)
		self.xstep_edit.editingFinished.connect(self.apply_changes)
		
		#==================== Create Labels ======================
		
		self.vspacer =  QSpacerItem(10, 10, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
		
		self.cp_lab = QLabel("Control Parameter:")
		self.cp_lab.setFont(label_font)
		self.cp_labval = QLabel(f"{self.sldr_widget.control_parameter}")
		
		self.unit_lab = QLabel("Units:")
		self.unit_lab.setFont(label_font)
		self.unit_labval = QLabel(f"{self.sldr_widget.unit_label}")
		
		#================ Apply to Grid ===================
		
		n1 = 0
		n2 = n1+3
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.xmin_label, n1+0, 0)
		self.grid.addWidget(self.xmin_edit, n1+0, 1)
		self.grid.addWidget(self.xmax_label, n1+1, 0)
		self.grid.addWidget(self.xmax_edit, n1+1, 1)
		self.grid.addWidget(self.xstep_label, n1+2, 0)
		self.grid.addWidget(self.xstep_edit, n1+2, 1)
		
		self.grid.addItem(self.vspacer, n2+0, 0)
		self.grid.addWidget(self.cp_lab, n2+1, 0, 1, 2)
		self.grid.addWidget(self.cp_labval, n2+2, 0, 1, 2)
		self.grid.addWidget(self.unit_lab, n2+3, 0)
		self.grid.addWidget(self.unit_labval, n2+3, 1)
		
		self.setLayout(self.grid)
	
	def apply_changes(self):
		
		# Read values from UI
		xstep = float(self.xstep_edit.text())
		xmin = float(self.xmin_edit.text())
		xmax = float(self.xmax_edit.text())
		
		# Save values to controller
		self.sldr_widget.set_maximum(xmax)
		self.sldr_widget.set_minimum(xmin)
		self.sldr_widget.set_step(xstep)

class BHIntegratedSliderSettingsWindow(QMainWindow):
	
	def __init__(self, slider_panel):
		super().__init__()
		
		self.slider_panel = slider_panel
		self.slider_dict = self.slider_panel.sliders
		
		self.setWindowTitle("Slider Settings")
		self.setFixedSize(325, 325)
		
		self.grid = QGridLayout()
		
		# Create tabs
		self.tab_bar = QTabWidget()
		for sldr in self.slider_dict.values():
			self.tab_bar.addTab(SliderSettingsWidget(sldr), f"Slider: {sldr.header_label_txt}")
			
		# Define grid
		self.grid.addWidget(self.tab_bar, 0, 0)
		
		self.cw = QtWidgets.QWidget()
		self.cw.setLayout(self.grid)
		self.setCentralWidget(self.cw)

class BHSliderPanel(QWidget):
	
	def __init__(self, main_window):
		super().__init__()
		self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
		
		self.main_window = main_window
		self.sliders = {}
		
		self.slider_settings_btn = QPushButton("Slider Settings", parent=self)
		self.slider_settings_btn.setFixedSize(100, 25)
		self.slider_settings_btn.clicked.connect(self.launch_settings_ui)
		
		self.slider_box = QGroupBox()
		self.slider_box.setStyleSheet("QGroupBox{border:0;}")
		self.slider_grid = QGridLayout()
		self.slider_box.setLayout(self.slider_grid)
		
		self.btn_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.slider_box, 0, 0, 1, 2)
		self.grid.addItem(self.btn_spacer, 1, 0)
		self.grid.addWidget(self.slider_settings_btn, 1, 1)
		
		self.setLayout(self.grid)
	
	def launch_settings_ui(self):
		
		self.settings_dialog = BHIntegratedSliderSettingsWindow(self)
		self.settings_dialog.show()
		
	def add_slider(self, swidget:BHSliderWidget):
		
		self.sliders[swidget.control_parameter] = swidget
		
		self.slider_grid.addWidget(swidget, 0, len(self.sliders)-1)
	
	def update_state(self, state):
		
		for k in self.sliders.keys():
			if k in state:
				self.sliders[k].set_slider_position(state[k])

class FileAnalyzerWorker(QObject):
	
	finished = pyqtSignal(str, dict)
	progress = pyqtSignal(int)
	
	def __init__(self, analysis_function, file):
		super().__init__()
		
		self.file = file
		self.analysis_function = analysis_function
		self.data = {}
		self.msg = ""
		
	def run(self):
		
		# Analyze the file
		try:
			self.msg, self.data = self.analysis_function(self.file)
			print(self.data)
		except Exception as e:
			self.main_window.log.error(f"An error occurred while analyzing the file >{self.file}<.", detail=f"{e}")
			self.finished.emit(f"Failed ({self.msg}). ({e})", {})
			return
		
		if not isinstance(self.data, dict):
			self.finished.emit(f"Failed ({self.msg}). Provided function returned None.",{})
			return
		
		self.finished.emit(f"Success ({self.msg})", self.data)

class FileAnalyzerFileTab(bh.BHListenerWidget):
	
	def __init__(self, main_window, plot_function, analysis_function, file):
		super().__init__(main_window=main_window)
		
		self.main_window = main_window
		self.analysis_function = analysis_function
		self.plot_function = plot_function
		self.file = file
		
		self.fig_tabs = QTabWidget(self.main_window)
		
		self.status_label = QLabel(f"Task status: Idle")
		
		self.grid = QGridLayout()
		self.grid.addWidget(self.fig_tabs, 0, 0)
		self.grid.addWidget(self.status_label, 1, 0)
		self.setLayout(self.grid)
		
		self.thread = None
		self.worker = None
		
		self.data = {}
		self.figs = []
		self.canvases = []
		self.toolbars = []
		self.combined = []
	
	def plot(self):
		''' This runs in the main thread and can safely run matplotlib GUI calls
		(and of course anythign else).'''
		
		# Run plot function in main thread. Will return a list of figures
		try:
			self.main_window.log.debug(f"Running plot function.", detail=f"data={self.data}")
			self.figs = self.plot_function(self.data, self.file)
		except Exception as e:
			self.main_window.log.error(f"Plot function encountered an error.", detail=f"{e}")
			return
		
		# Check for bad return
		if self.figs is None:
			self.main_window.log.error(f"Plot function returned None.")
			return
		
		# Make a new tab for each figure 
		for f in self.figs:
			
			# Create GUI plot
			self.canvases.append(FigureCanvas(f))
			self.toolbars.append(NavigationToolbar2QT(self.canvases[-1], self))
			
			combo = QWidget()
			subgrid = QGridLayout()
			subgrid.addWidget(self.toolbars[-1], 0, 0)
			subgrid.addWidget(self.canvases[-1], 1, 0)
			combo.setLayout(subgrid)
			self.combined.append(combo)
			
			# Get tab name
			fig_name = f"Figure {f.number}"
			
			# Add to tab
			self.fig_tabs.addTab(combo, fig_name)
	
	def process(self):
		''' Runs the analysis (in second thread, only if 2nd function given) and
		plot (in main thread) as soon as possible.
		'''
		
		# Check if user wants to skip parallel phase
		if self.analysis_function is None:
			self.main_window.log.debug("Skipping parallel phase. No analysis function provided.")
			
			# Run plot immediately
			self.plot()
			return
		
		self.main_window.log.debug("Preparing to launch analysis thread...")
		
		# Otherwise launch thread
		if self.thread is None:
			
			# Prepare thread and worker
			self.thread = QThread()
			self.worker = FileAnalyzerWorker(self.analysis_function, self.file)
			self.worker.moveToThread(self.thread)
			self.worker.finished.connect(self.analysis_finished)
			self.thread.started.connect(self.worker.run)
			
			self.main_window.log.debug(f"Beginning thread to analyze file >{self.file}<")
			self.status_label.setText("Task Status: Running...")
			
			# Start thread
			self.thread.start()
	
	def analysis_finished(self, message:str, data:dict):
		
		self.data = data
		
		self.main_window.log.debug(f"Thread finished.", detail=f"Received data={self.data}")
		
		self.status_label.setText(f"Task Status: finished. [{message}].")
		
		# self.toolbars.append(NavigationToolbar2QT(self.canvases[-1], ))
		
		self.thread.quit()
		self.thread.wait()
		self.thead = None
		self.worker = None
		
		self.plot()

class FileAnalyzerWidget(bh.BHListenerWidget):
	''' This widget was developed for the script Pioneer, but is more broadly
	useful. It just accepts files to be dragged and dropped in, and they will
	be fed to a specified function to be processed. The function will return plots
	which will be displayed as various tabs.
	'''
	
	def __init__(self, main_window, plot_function:callable, analysis_function:callable):
		super().__init__(main_window)
		
		self.main_window = main_window
		self.setAcceptDrops(True) # Enable files to be dropped in
		self.plot_function = plot_function
		self.analysis_function = analysis_function
		
		# Create tab for each file
		self.file_tab_widget = bh.BHTabWidget(self.main_window)
		
		# Specify layout
		self.grid = QGridLayout()
		self.grid.addWidget(self.file_tab_widget, 0, 0)
		self.setLayout(self.grid)
	
	def abbrev_filename(self, filename:str):
		''' This function can be overridden if you want to change how filenames
		are handled when naming tabs.'''
		
		return os.path.basename(filename)
	
	def analyze_file(self, file):
		
		# Create new tab object - this handles creating a new thread to do the analysis in.
		new_tab = FileAnalyzerFileTab(self.main_window, self.plot_function, self.analysis_function, file)
		new_tab.process()
		
		# Add to tab widget
		self.file_tab_widget.addTab(new_tab, self.abbrev_filename(file))
	
	def dragEnterEvent(self, event):
		if event.mimeData().hasUrls():
			event.accept()
		else:
			event.ignore()
	
	def dropEvent(self, event):
		files = [url.toLocalFile() for url in event.mimeData().urls()]
		for f in files:
			self.main_window.log.info(f"File >{f}< dropped into FileAnalyzerWidget with analysis function >{self.analysis_function}<.")
			
			self.analyze_file(f)