import blackhole.widgets as bhw
import blackhole.base as bh
import pandas as pd

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup, QDoubleValidator, QIcon, QFontDatabase, QFont, QPixmap
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QGridLayout, QLineEdit, QCheckBox, QSpacerItem, QSizePolicy, QMainWindow, QSlider, QPushButton, QGroupBox, QListWidget, QFileDialog, QProgressBar, QStatusBar

import pylogfile.base as plf
import numpy as np
import sys

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--detail', help="Show log details.", action='store_true')
parser.add_argument('--loglevel', help="Set the logging display level.", choices=['LOWDEBUG', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], type=str.upper)
args = parser.parse_args()

# Initialize log
log = plf.LogPile()
if args.loglevel is not None:
	print(f"\tSetting log level to {args.loglevel}")
	log.set_terminal_level(args.loglevel)
else:
	log.set_terminal_level("DEBUG")
log.str_format.show_detail = args.detail

#==================== Define control parameters =======================

AMPLITUDE_CTRL = "amplitude"

#===================== Custom Functions for plotting ==================



##==================== Create custom classes for Black-Hole ======================

class ChirpDataset(bh.BHDataset):
	
	def __init__(self, log:plf.LogPile, source_info:bh.BHDataSource):
		super().__init__(log, source_info.unique_id)
		
		self.time_ns = []
		self.volt_mV = []
		
		master_df = pd.read_csv(source_info.file_fullpath, skiprows=4, encoding='utf-8')
		# trim_regions_orig = [[-400, -350], [-300, -225], [-190, -125]]
		
		self.time_ns = master_df['Time']*1e9
		self.volt_mV = master_df['Ampl']*1e3
		
class ChirpAnalyzerMainWindow(bh.BHMainWindow):
	
	def __init__(self, log, app, data_manager):
		super().__init__(log, app, data_manager, window_title="Chirp Analyzer")
		
		self.main_grid = QGridLayout()
		
		# Create select widget
		self.select_widget = bh.BHDatasetSelectBasicWidget(data_manager, log)
		
		#TODO: Create a useful widget
		self.plot = bhw.BHPlotWidget(self.control_requested, custom_render_func=render_sine)
		self.add_control_subscriber(self.plot)
		
		#TODO: Create a controller
		self.slider = bhw.BHSliderWidget(self, param=AMPLITUDE_CTRL, header_label="Slider 1", initial_val=2, min=1, max=10, step=1, unit_label="V", tick_step=1)
		
		# Position widgets
		self.main_grid.addWidget(self.plot, 0, 0)
		self.main_grid.addWidget(self.slider, 0, 1)
		self.main_grid.addWidget(self.select_widget, 1, 0)
		
		# Create central widget
		self.central_widget = QtWidgets.QWidget()
		self.central_widget.setLayout(self.main_grid)
		self.setCentralWidget(self.central_widget)
		
		self.show()

##==================== Create custom functions for Black-Hole ======================

time = np.linspace(0, 10, 101)
omega = 2*np.pi*0.5

def load_chirp_dataset(source, log):
	return ChirpDataset(log, source)


def render_sine(plot_widget):
	global time
	
	# Calculate sine
	ampl = plot_widget.control_requested.get_param(AMPLITUDE_CTRL)
	y = np.sin(time*omega)*ampl
	
	# Clear old data
	plot_widget.ax1a.cla()
	
	# Replot
	plot_widget.ax1a.plot(time, y, linestyle=':', marker='.', color=(0.65, 0, 0))
	plot_widget.ax1a.set_xlabel("Time (ns)")
	plot_widget.ax1a.set_ylabel("Amplitude (mV)")
	plot_widget.ax1a.set_ylim([-15, 15])
	plot_widget.ax1a.grid(True)
	plot_widget.ax1a.set_title("Sine")
	

#================= Basic PyQt App creation things =========================

# Create app object
app = QtWidgets.QApplication(sys.argv)
app.setStyle(f"Fusion")
# app.setWindowIcon

# Create Data Manager
data_manager = bh.BHDatasetManager(log, load_function=load_chirp_dataset)
if not data_manager.load_configuration("conf_sine_example.json"):
	exit()

window = ChirpAnalyzerMainWindow(log, app, data_manager)

app.exec()