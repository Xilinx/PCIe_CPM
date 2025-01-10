# Copyright (C) 2024, Advanced Micro Devices, Inc. All rights reserved. 
# SPDX-License-Identifier: MIT


from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QPushButton, QLabel, QMessageBox,
    QFileDialog, QScrollArea, QVBoxLayout, 
    QHBoxLayout,QTextEdit, QTableWidget,
    QTableWidgetItem, QTabWidget, QComboBox,
    QProgressBar, QFormLayout, QTabWidget,
    QFileDialog, QHeaderView, QListWidgetItem,
    QGridLayout, QLineEdit
)
from PyQt5 import uic, QtCore, QtGui, QtWidgets
from PyQt5.QtGui import (
                         QPixmap, QTextCursor, QFont, 
                         QFontMetrics, QIcon, QDesktopServices, 
                         QStandardItem, QStandardItemModel, QMovie
)

from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal, QUrl, pyqtSlot


QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)


from chipscopy.api.ibert.aliases import (
    EYE_SCAN_HORZ_RANGE,
    EYE_SCAN_VERT_RANGE,
    EYE_SCAN_VERT_STEP,
    EYE_SCAN_HORZ_STEP,
    EYE_SCAN_TARGET_BER,
    PATTERN,
    RX_LOOPBACK,
    TX_PRE_CURSOR,
    TX_POST_CURSOR,
    TX_DIFFERENTIAL_SWING,
    RX_TERMINATION_VOLTAGE,
    RX_COMMON_MODE
)

from chipscopy import create_session, delete_session, report_versions, report_hierarchy, get_design_files
from chipscopy.api.ibert import create_eye_scans, create_links, delete_eye_scans, delete_links
import sys
import os

import time
from io import StringIO
from typing import List
import re
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import webbrowser

import import_ipynb
from device_file import VersalSession
from thread_file import ProgrammingWorker, RegisterReadWorker, LTSSM_Worker, IbertWorker, ILA_Worker
#from register_parser_window import Ui_RegisterParserWindow, browse_file
from register_parser_window import ParserModel, RegisterParserController, RegisterParserGUI
from functools import partial
import sip




if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)



    
def show_error_message(message: str) -> None:
    """
    Show error message to the user when called.
    """
    QMessageBox.warning(None, "Error", message)

def show_informative_message(message: str) -> None:
    """
    Display informative message to the user when called
    """

    QMessageBox.information(None, "Information", message)

    
def start_worker_thread(window: object, worker_name: str, thread_name: str, connections: {}, execute_upon_startup: []):
    """
    Starts a worker thread in the specified window object.

    This function initializes and starts a worker thread in the specified window object.
    It sets up signal-slot connections and performs any specified actions when the
    thread is started.

    Args:
        window (object): 
            The window object in which the worker thread will be started.
        worker_name (str): 
            The name of the worker object attribute in the window object.
        thread_name (str): 
            The name of the thread object attribute in the window object.
        connections (dict): 
            A dictionary of signal-slot connections to be established.
            Each key-value pair represents a signal emitted by the worker and the corresponding
            slot(s) to be connected to the signal. If multiple slots need to be connected,
            provide them as a list. If no connections are required, pass empty {}
        started_action (list): 
            A list of actions to be performed when the thread is started.
            Each action in the list should be a callable object (e.g., function, method) that
            will be triggered when the thread starts. If no actions are required, pass empty [].

    Raises:
        None

    Returns:
        None

    Example usage:
        connections = {
            'progress_signal': [window.update_progress_bar, window.log_progress],
            'finished_signal': window.process_thread_results
        }
        started_events = [window.init_thread_resources]
        
        start_worker_thread(main_window, 'worker', 'thread', connections, started_action)
    """

    setattr(window, thread_name, QThread())
    getattr(window, worker_name).moveToThread(getattr(window, thread_name))
    
    
    if connections is not None:
        for signal, slots in connections.items():
            signal_obj = getattr(getattr(window, worker_name), signal)

            if isinstance(slots, list):
                for slot in slots:
                    signal_obj.connect(slot)
     
            
    thread_obj = getattr(window, thread_name)
    
    if execute_upon_startup is not None:
        for executable_func in execute_upon_startup:
            thread_obj.started.connect(executable_func)
    
    thread_obj.start()
    

def delete_thread_safely(window: object, worker_name: str, thread_name:str):
    """
    Safely deletes a thread associated with a worker object in a window.

    This function is used to terminate and clean up a running thread
    associated with a worker object in a given window. It ensures the thread
    is properly terminated and sets the associated worker and thread objects
    to None, indicating their deletion.

    Args:
        window (object): The window object containing the worker and thread
            objects.
        worker_name (str): The name of the worker object to be deleted.
        thread_name (str): The name of the thread object to be deleted.

    Raises:
        None

    Returns:
        None

    Example usage:
        delete_thread_safely(main_window, 'worker', 'thread')

    Note:
        This function assumes that the window object has attributes with the
        specified worker and thread names. It checks if the thread is running
        and terminates it by calling `quit()` and `wait()` methods. It then
        sets the worker and thread objects to None, indicating their deletion.
        Finally, it prints a confirmation message stating that the thread has
        been successfully deleted.
    """
    worker = getattr(window, worker_name, None)
    thread = getattr(window, thread_name, None)
    print(f"trying to delete {worker} {thread}")
    if thread and thread.isRunning():
        thread.quit()
        thread.wait()
        setattr(window, worker_name, None)
        setattr(window, thread_name, None)
        print(f"Deleted {thread_name}")

    
    


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi("ui_designs/versal_design.ui",self)
        self.setWindowTitle("Versal ACAP Debug Analyzer v1.0")
        self.setFixedSize(self.size())
        self.stackedWidget.setCurrentIndex(0)
        self.apply_images_to_gui()
        self.setup_gui_buttons()
        self.clear_device_properties_frame()
        self.initialize_attributes()
        self.ILA_TABS.setTabEnabled(1,False)
        self.ILASignal_Table.setColumnCount(1)
        self.setTextWithVerdana(widget = self.captureSetup_Label, font_size = 10, 
                                text = "Signal capture setup empty. "
                                "Select a signal from the Table and press 'Add Signal'")
        
        #self.captureSetup_gridLayout = QGridLayout()
        
        
    
           

    def initialize_attributes(self):
        # Base object that will hold all core attributes
        self.versal = None
        
        self.scanning_worker = None
        
        self.pdi_file = None
        self.ltx_file = None
        
        
        # NPI Register Page - Attributes
        self.REG_ADDRESSES = None
        self.MEMORY_TARGET = None
        self.READ_SIZE = None
        
        self.programming_worker = None
        self.programming_thread = None
        self.ibert_worker = None
        self.RegisterWorker = None
        self.register_worker_records_html = None
        
        
        # IBERT PCIe Page - Attributes
        self.combo_boxes = []
        self.eye_progress_bars = []
        self.combined_link_layout = QVBoxLayout()
        self.eye_progress_bars_layout = QFormLayout()
        self.linkPropertiesWidgets = []
        self.eye_scan_tabs = []
        self.eyeScanStatus_Labels_Layout_ls = []
        
        
         # LTSSM Page - Attributes
        self.ltssm_worker = None
        self.ltssm_thread = None
        ########################
        
        # ILA Page - Attributes
        self.ila_worker = None
        self.ila_thread = None
        self.signals_ls = set()
        self.trigger_status = False
       
        #self.ila_core_signals = []
        
        
        self.ila_capture_mode = self.ILACaptureMode_comboBox.currentText()
        self.ila_probe_operator = None
        self.ila_probe_value = None
        self.ila_trigger_mode = self.ILACaptureMode_ComboBox.currentText()
        self.ila_window_count = None
        self.ila_data_depth = None
        self.ila_trigger_position = None
        
        ########################
        
        # CSV Register Parser - Attributes
        self.register_def_file = None
        self.register_val_file = None
        ##############################
        
        
    def setup_gui_buttons(self):
        
        app = QApplication.instance()
        app.aboutToQuit.connect(self.realtime_register_reading_finished_app_closing)
        app.aboutToQuit.connect(self.delete_ltssm_thread_upon_app_exit)
        app.aboutToQuit.connect(self.delete_ila_thread_upon_app_exit)
        
        
        # Page Switching Buttons:
        self.MAIN_MENU_BUTTON.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.NPI_REGISTER_BUTTON.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.IBERT_PCIE_BUTTON.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(2))
        self.LTSSM_BUTTON.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(3))
        self.ILA_BUTTON.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(4))
        self.REGISTER_PARSER_BUTTON.clicked.connect(self.open_register_parser_window)
        
        # Main Menu Page Buttons
        self.connectServer_Button.clicked.connect(self.connect_server)
        self.programDesign_Button.clicked.connect(self.program_device)
        self.refresh_device_properties_button.clicked.connect(self.scan_and_display_device_properties)
        self.clearAllMainMenu_Button.clicked.connect(self.clear_all_settings_to_default)
        
        # NPI Register Page Buttons
        self.startReading_Button.clicked.connect(self.initiate_realtime_register_reading)
        self.stopReading_Button.clicked.connect(self.stop_realtime_register_reading)
        self.writeValues_Button.clicked.connect(self.write_to_registers)
        self.clearReading_Button.clicked.connect(self.clear_reading_registers)
        self.extractRegisters_Button.clicked.connect(self.extract_csv_file)
        self.extractRegisterFromCSV_Button.clicked.connect(self.extract_registers_from_csv)
        
        self.phyRdy_Button.clicked.connect(self.extract_phyrdy_register)
        self.gtResetFsm_Button.clicked.connect(self.extract_gt_reset_fsm_register)
        self.ltssm_button.clicked.connect(self.extract_ltssm_register)
        self.openRegisterRecords_Button.clicked.connect(self.open_register_records_file)
        self.registerDebuggingArticle_Button.clicked.connect(self.open_register_debugging_article)
        
        
        # IBERT PCIe Page Buttons
        self.setLinkPropertiesButton.clicked.connect(self.set_link_properties)
        self.startEyeScanButton.clicked.connect(self.start_eye_scans)
        
        #LTSSM Page Buttons
        self.displayLTSSM_Button.clicked.connect(self.start_ltssm_thread)
        self.stopRefreshingLTSSM_Button.clicked.connect(self.stop_ltssm_thread)
        self.resetPcieCore_Button.clicked.connect(self.reset_pcie_core)
        
        # ILA Page Buttons
        self.selectILACore_Button.clicked.connect(self.display_core_signals)
        self.addSignal_Button.clicked.connect(self.add_signal_to_capture_setup)
        self.ILACaptureMode_comboBox.currentTextChanged.connect(self.set_ila_capture_mode)
        self.ILACaptureMode_comboBox.currentTextChanged.connect(self.set_ila_trigger_mode)
        self.startTrigger_Button.clicked.connect(self.start_ila_triggering_process)
        self.stopTrigger_Button.clicked.connect(self.stop_ila_thread)
        
        
        self.ILASignal_Table.verticalScrollBar().valueChanged.connect(self.__update_ila_scrollbars)
        self.ILASignalValue_Table.verticalScrollBar().valueChanged.connect(self.__update_ila_scrollbars)
        self.ILASignalData_Table.verticalScrollBar().valueChanged.connect(self.__update_ila_scrollbars)
        self.clear_ila_data_Button.clicked.connect(lambda: self.clear_table_rows(self.ILASignalValue_Table))
        self.clear_ila_data_Button.clicked.connect(lambda: self.clear_table_rows(self.ILASignalData_Table))
        self.ILAWindowCount_lineEdit.textEdited.connect(self.update_user_on_ila_core_static_info)
        self.ILADataDepth_lineEdit.textEdited.connect(self.update_user_on_ila_core_static_info)
        #self.basicTrigger_checkBox.stateChanged.connect(self.trigger_checkbox_changed)
        #self.immediateTrigger_checkBox.stateChanged.connect(self.trigger_checkbox_changed)
        #self.trigger_Button.clicked.connect(self.check_trigger_status)
        #self.stopTrigger_Button.clicked.connect(self.stop_ila_thread)
        #self.dataDisplayTrigger_Button.clicked.connect(self.check_trigger_status)
        #self.dataDisplayStop_Button.clicked.connect(self.stop_ila_thread)
        #self.oneTimeTrigger_checkBox.clicked.connect(self.update_trigger_loop)
       # self.continuousTrigger_checkBox.clicked.connect(self.update_trigger_loop)
        
        
        
    
    def apply_images_to_gui(self):
        self.ltssmStatus_Label.setStyleSheet("image: url(:/logos/stop_read_icon.png);")
        #self.amd_logo_frame.setStyleSheet("image: url(:/logos/AMD_Logo.png);")
        self.connectServer_Button.setIcon(QIcon(":/logos/connect_logo.png"))
        self.programDesign_Button.setIcon(QIcon(":/logos/programming.png"))
        self.NPI_REGISTER_BUTTON.setIcon(QIcon(":/logos/register_icon.png"))
        self.IBERT_PCIE_BUTTON.setIcon(QIcon(":/logos/eye_scan.png"))
        self.LTSSM_BUTTON.setIcon(QIcon(":/logos/state_machine.png"))
        self.ILA_BUTTON.setIcon(QIcon(":/logos/logic_analyzer.png"))
        self.MAIN_MENU_BUTTON.setIcon(QIcon(":/logos/main_menu.png"))
        self.titleLabel.setIcon(QIcon(":/logos/chipscopy_logo.png"))
        self.writeValues_Button.setIcon(QIcon(":/logos/write_icon.png"))
        self.startReading_Button.setIcon(QIcon(":/logos/read_register_icon.png"))
        self.stopReading_Button.setIcon(QIcon(":/logos/stop_read_icon.png"))
        self.clearReading_Button.setIcon(QIcon(":/logos/clear.png"))
        self.extractRegisters_Button.setIcon(QIcon(":/logos/extract_files_icon.png"))
        self.IBERT_TreeView_LabelButton.setIcon(QIcon(":/logos/treeViewLogo.png"))
        self.LinkProperties_LabelButton.setIcon(QIcon(":/logos/down_arrow_icon.png"))
        self.EyeScanProgress_LabelButton.setIcon(QIcon(":/logos/down_arrow_icon.png"))
        self.setLinkPropertiesButton.setIcon(QIcon(":/logos/connect_logo.png"))
        self.startEyeScanButton.setIcon(QIcon(":/logos/eye_scan.png"))
        self.displayLTSSM_Button.setIcon(QIcon(":/logos/read_register_icon.png"))
        self.stopRefreshingLTSSM_Button.setIcon(QIcon(":/logos/stop_read_icon.png"))
        self.resetPcieCore_Button.setIcon(QIcon(":/logos/reset.png"))
        self.InputRegistersRead_ButtonAsLabel.setIcon(QIcon(":/logos/down_arrow_icon.png"))
        self.REGISTER_PARSER_BUTTON.setIcon(QIcon(":/logos/icon-register.png"))
        
        self.startTrigger_Button.setIcon(QIcon("GUI_Logos/trigger_icon_2.png"))
        self.stopTrigger_Button.setIcon(QIcon("GUI_Logos/stop_read_icon.png"))
        self.addSignal_Button.setIcon(QIcon("GUI_Logos/add_icon.png"))
        self.clear_ila_data_Button.setIcon(QIcon("GUI_Logos/clear.png"))
        #self.trigger_Button.setIcon(QIcon(":/logos/programming.png"))
       # self.stopTrigger_Button.setIcon(QIcon(":/logos/stop_read_icon.png"))
        #self.dataDisplayTrigger_Button.setIcon(QIcon(":/logos/programming.png"))
        #self.dataDisplayStop_Button.setIcon(QIcon(":/logos/stop_read_icon.png"))
        
        
        self.ilaLoading_Movie = self.set_movie_for_label(self.ila_loading_Label, "GUI_Logos/red_icon_for_ltssm.png")
        self.stop_movie(self.ilaLoading_Movie)
        
        self.registerLoading_Movie = self.set_movie_for_label(self.registerLoadingLabel, "GUI_Logos/red_icon_for_ltssm.png")
        self.stop_movie(self.registerLoading_Movie)
        
        
       

        
      
        
        
    def set_movie_for_label(self, label, movie_path):
        movie = QMovie(movie_path)
        movie.setScaledSize(label.size())
        label.setMovie(movie)
        movie.start()
        return movie
    
    def stop_movie(self, movie):
        movie.stop()
        
  

    def open_register_parser_window(self):
        
    
        self.registerParserController = RegisterParserController(RegisterParserGUI(), ParserModel())
        self.registerParserController.display_gui()
        
        #self.registerParserWindow = QtWidgets.QWidget()
        #self.registerParserUi = Ui_RegisterParserWindow()
        #self.registerParserUi.setupUi(self.registerParserWindow)
        #self.registerParserWindow.show()
        
    
    def setTextWithVerdana(self, widget, font_size:int, text:str):
        font = QFont("Verdana", font_size)
        widget.setFont(font)
        widget.setText(text)
        
    def clear_table_rows(self, table_widget):
        while table_widget.rowCount() > 0:
            table_widget.removeRow(0)
            
            
    def set_ila_capture_mode(self, capture_mode:str):
        self.ila_capture_mode = capture_mode
    
    def set_ila_trigger_mode(self, trigger_mode:str):
        self.ila_trigger_mode = trigger_mode
    
    def display_core_signals(self):
        
        if self.versal is None:
            show_informative_message("No session established!")
            return
        
        if self.versal.device is None:
            show_informative_message("No connection made to the Versal Device!")
        
        self.versal.selected_ila = self.versal.device.ila_cores.filter_by(name = self.ILACores_ComboBox.currentText()[3:])[0]
       
        
        if self.versal.selected_ila is None:
            show_error_message("No signals available for this core!")
            return
        
        
            
        
        self.setTextWithVerdana(widget = self.selectedCore_lineEdit, font_size = 10, text = str(self.versal.selected_ila))
        self.clear_table_rows(self.ILASignal_Table)
        self.clear_table_rows(self.ILASignalValue_Table)
        self.clear_table_rows(self.ILASignalData_Table)
        #self.clear_gridLayout(self.captureSetup_gridLayout)
        
        for i, probe in enumerate(self.versal.selected_ila.probes):
            

            if i < self.ILASignal_Table.rowCount():
                self.ILASignal_Table.setItem(i, 0, QTableWidgetItem(str(probe)))
                
            else:
                # If the table doesn't have enough rows, add a new row and then set the item
                self.ILASignal_Table.insertRow(i)
                self.ILASignal_Table.setItem(i, 0, QTableWidgetItem(str(probe)))
            color = self.getColor(i)
            self.setColortoRow(self.ILASignal_Table, i, color)
            
        print("Stat info: ",self.versal.selected_ila.static_info)
        self.ILADataDepth_lineEdit.setPlaceholderText(f"Max depth: {int(self.versal.selected_ila.static_info.data_depth)}")
        self.ILATriggerPosition_lineEdit.setPlaceholderText(f"Halfway point: {int(self.versal.selected_ila.static_info.data_depth / 2)}")
        
    def update_user_on_ila_core_static_info(self):
        window_count = 0
        if len(self.ILAWindowCount_lineEdit.text()) == 0:
            window_count = 1
        else:
            window_count = int(self.ILAWindowCount_lineEdit.text())
                           
        data_depth = self.versal.selected_ila.static_info.data_depth // window_count
        halfway_point = data_depth // 2
        self.ILADataDepth_lineEdit.setPlaceholderText(f"Max depth: {data_depth}")
        self.ILATriggerPosition_lineEdit.setPlaceholderText(f"Halfway point: {halfway_point}")
        
    
    
    
    def replace_format_to_csv(self, filepath):
        if len(filepath) == 0:
            return None
        
        if not filepath.endswith(".csv"):
            split = filepath.split(".")
            if isinstance(split, list):
                filepath = split[0] + ".csv"
            else:
                filepath += ".csv"
        return filepath        
    def start_ila_triggering_process(self):
        
        if self.versal is None:
            show_error_message("No connection has been made with the device")
            return
        
        if self.ILACores_ComboBox.count() == 0:
            show_error_message("No ILA Cores available to select!")
            return
        
        if self.ILAWindowCount_lineEdit.text() == "":
            show_error_message("Missing information on Window Count [Settings]")
            return
        
        if self.ILADataDepth_lineEdit.text() == "":
            show_error_message("Missing information on Window Data Depth [Settings]")
            return
        
        if self.ILATriggerPosition_lineEdit.text() == "":
            show_error_message("Missing information on Trigger Position [Settings]")
            return
        
        ila_capture_mode = self.ILACaptureMode_comboBox.currentText()
        ila_trigger_mode = self.ILACaptureMode_ComboBox.currentText()
        
        ila_window_count = self.try_get_integer_input(self.ILAWindowCount_lineEdit)
        ila_data_depth = self.try_get_integer_input(self.ILADataDepth_lineEdit)
        ila_trigger_position = self.try_get_integer_input(self.ILATriggerPosition_lineEdit)
        
        csv_file_path = self.CSVILARecordFile_LineEdit.text()
        csv_file_path = self.replace_format_to_csv(csv_file_path)
        
        flag = ila_capture_mode == "One Time Capture"
            
            
        ila_connections = {
            "dataframe_signal":[self.start_ila_capture],
            "error":[self.display_ila_capture_error],
            "ila_core_status":[self.update_ila_core_status],
            "ila_is_armed_status":[self.update_ila_armed_status],
            "csv_file_size_signal":[self.update_ila_csv_file_size],
            "finished":[self.reset_ila_thread]
        }
        
        
        self.ila_worker = ILA_Worker(versal = self.versal,
                                     capture_mode_bool = flag,
                                     trigger_mode = ila_trigger_mode,
                                     window_count = ila_window_count,
                                     data_depth = ila_data_depth,
                                     trigger_position = ila_trigger_position,
                                     csv_file = csv_file_path)
        
    
        startup_connection = self.get_startup_connection(ila_trigger_mode)
        
        start_worker_thread(window = self, 
                            worker_name = "ila_worker", 
                            thread_name = "ila_thread",
                            connections = ila_connections,
                            execute_upon_startup = startup_connection)
        
        self.ilaLoading_Movie = self.set_movie_for_label(self.ila_loading_Label, "GUI_Logos/loading_movie.gif")
        self.startTrigger_Button.setEnabled(False)
        self.clear_table_rows(self.ILASignalValue_Table)
        self.clear_table_rows(self.ILASignalData_Table)
        
    def try_get_integer_input(self, line_edit):
        try:
            return int(line_edit.text())
        except Exception as ex:
            show_informative_message(str(ex))
            return None
        
    def get_startup_connection(self, trigger_mode):
        if trigger_mode == "Basic Trigger":
            return [self.ila_worker.run_basic_trigger]
        if trigger_mode == "Immediate Trigger":
            return [self.ila_worker.run_immediate_trigger]
        return []
    
    def __update_ila_scrollbars(self, index):
        self.ILASignal_Table.verticalScrollBar().setValue(index)
        self.ILASignalValue_Table.verticalScrollBar().setValue(index)
        self.ILASignalData_Table.verticalScrollBar().setValue(index)
        
        
        
    @pyqtSlot(str)
    def update_ila_core_status(self, status:str):
        self.setTextWithVerdana(widget = self.coreStatus_lineEdit, font_size = 10, text = status)
        
    @pyqtSlot(int)
    def update_ila_armed_status(self, val:int):
        self.ILACoreStatus_ProgressBar.setValue(val)
        
    @pyqtSlot(str)
    def update_ila_csv_file_size(self, mb_size:str):
        self.CSVFileSize_lineEdit.setText(mb_size)
        
        #self.setTextWithVerdana(widget = self.CSVFileSize_lineEdit, font_size = 10, text = mb_size)
                                
        
        
        
        
        
    
    
    def reset_ila_thread(self):
        delete_thread_safely(window = self, worker_name = "ila_worker", thread_name = "ila_thread")
        self.stop_movie(self.ilaLoading_Movie)
        self.ilaLoading_Movie = self.set_movie_for_label(self.ila_loading_Label, "GUI_Logos/red_icon_for_ltssm.png")
        self.stop_movie(self.ilaLoading_Movie)
        self.startTrigger_Button.setEnabled(True)
        
    def stop_ila_thread(self):
        if self.ila_worker is None:
            show_informative_message("No ILA Capture Running!")
            return
        
        if self.ila_thread.isRunning():
           # self.stop_requested = True
            
            self.ila_worker.breakByButton = True
            
            
    def delete_ila_thread_upon_app_exit(self):
        if self.ila_worker:
            self.ila_worker.breakByButton = True
            
            
            
    def display_ila_capture_error(self, error):
        show_informative_message(error)
        self.reset_ila_thread()
        
        
                
    def add_signal_to_capture_setup(self):
        try:
            selected_item = self.ILASignal_Table.selectedItems()[0]
        except IndexError:
            show_informative_message("No signal was selected!")
            return
        
        signal = str(selected_item.text())
        signal_index = int(selected_item.row()) + 1
        
        if signal in self.versal.ILA_selected_signals:
            show_informative_message("Signal already added!")
            return
        

        if len(self.versal.ILA_selected_signals) >= 5:
            show_informative_message("Too many signals selected, MAX is 5!")
            return
      
        self.versal.ILA_selected_signals.append(signal)
        
        
        row_count = self.captureSetup_gridLayout.rowCount() 
        visible_row_count = self.captureSetup_gridLayout.count() // self.captureSetup_gridLayout.columnCount()  
        
        
        if len(self.versal.ILA_selected_signals) == 1:
            signal_title = QLineEdit("Signal Name")
            signal_title.setStyleSheet(("background-color: light silver;"))
            signal_title.setAlignment(Qt.AlignCenter)
            operator_title = QLineEdit("Operator")
            operator_title.setStyleSheet(("background-color: light silver;"))
            operator_title.setAlignment(Qt.AlignCenter)
            value_title = QLineEdit("Value")
            value_title.setStyleSheet(("background-color: light silver;"))
            value_title.setAlignment(Qt.AlignCenter)
            self.captureSetup_gridLayout.addWidget(signal_title, 1, 0)
            self.captureSetup_gridLayout.addWidget(operator_title,1,1)
            self.captureSetup_gridLayout.addWidget(value_title,1,2)
            
          
        
        
        signal_label = QLabel(f"{signal_index}: {signal}")
        operator_combo_box = QComboBox()
        value_combo_box = QComboBox()
        delete_button = QPushButton("Delete")
        

        operator_combo_box.addItems(["== (Equal)", "!= (Not Equal)", "< (Less than)", "<= (Equal or less than)",
                                     "> (Greater than)", ">= (Equal or Greater than)", "|| (Reduction OR)"])
        value_combo_box.addItems(["X (Don’t care)","0 (Zero)","1 (One)","F (Falling. Transition 1 -> 0)",
                                  "R (Rising. Transition 0 -> 1)","L (Laying. Opposite to R.)",
                                  "S (Staying. Opposite to F.)","B (Either Falling or Rising.)","N (No change. Opposite to B.)"])
        
        operator_combo_box.currentTextChanged.connect(
            lambda text, 
            operator_combo = operator_combo_box, 
            value_combo = value_combo_box,
            signal = signal: 
            self.update_probe_operator_and_value(text, operator_combo_box, value_combo_box, signal))

        # Connect value combo box
        value_combo_box.currentTextChanged.connect(
             lambda text, 
            operator_combo = operator_combo_box, 
            value_combo = value_combo_box,
            signal = signal: 
            self.update_probe_operator_and_value(text, operator_combo_box, value_combo_box, signal))
        
        self.captureSetup_gridLayout.addWidget(signal_label, row_count + 1, 0)
        self.captureSetup_gridLayout.addWidget(operator_combo_box, row_count + 1, 1)
        self.captureSetup_gridLayout.addWidget(value_combo_box, row_count + 1, 2)
        self.captureSetup_gridLayout.addWidget(delete_button, row_count + 1, 3)
        delete_button.clicked.connect(partial(self.delete_row, row_count + 1, signal))
        
        
        self.captureSetup_Frame.setLayout(self.captureSetup_gridLayout)
        
        self.captureSetup_Label.setVisible(False)
       
        
        
        
    def update_probe_operator_and_value(self, text, operator_combo, value_combo, signal):
        sender = self.sender()
        print(sender.currentText())
        
        if self.versal.selected_ila:
            self.versal.selected_ila.set_probe_trigger_value(name = str(signal),
                                                             trigger_value = [operator_combo.currentText()[:2].replace(" ",""), 
                                                                             value_combo.currentText()[:2].replace(" ","")]
                                                             )
                                                      
                                               
        
        

    def delete_row(self, actual_row_index, signal):     # layout, signal):
        
        for col in range(self.captureSetup_gridLayout.columnCount()):
            item = self.captureSetup_gridLayout.itemAtPosition(actual_row_index, col)
            if item:
                item = item.widget()
                self.captureSetup_gridLayout.removeWidget(item)
                #item.setParent(None)
                sip.delete(item)
        self.versal.ILA_selected_signals.remove(signal)
        
        
        
        if len(self.versal.ILA_selected_signals) == 0:
            self.clear_gridLayout(self.captureSetup_gridLayout)
            self.captureSetup_Label = QLabel("Signal capture setup empty. "
                                "Select a signal from the Table and press 'Add Signal'")
            self.setTextWithVerdana(widget = self.captureSetup_Label, font_size = 10, 
                                text = "Signal capture setup empty. "
                                "Select a signal from the Table and press 'Add Signal'")
            self.captureSetup_gridLayout.addWidget(self.captureSetup_Label,1,1)
            self.captureSetup_Label.setVisible(True)
            self.captureSetup_Label.setAlignment(Qt.AlignCenter)
            
            
        
        
     
    def clear_gridLayout(self,gridLayout):
        for row in range(gridLayout.rowCount()):
            for col in range(gridLayout.columnCount()):
                item = gridLayout.itemAtPosition(row, col)
                if item:
                    widget = item.widget()
                    gridLayout.removeWidget(widget)
                   # widget.setParent(None)
                    sip.delete(widget)

     
    @pyqtSlot(pd.DataFrame)
    def start_ila_capture(self, df):
        try:
            
            
            
            column_count = len(df.columns)
            row_count = len(df)
            #self.ila_worker.table_range = self.ila_worker.table_range + row_count

            #self.ILASignalValue_Table.setColumnCount(2)
            self.ILASignalValue_Table.setRowCount(column_count)
            self.ILASignalData_Table.setColumnCount(row_count)
            self.ILASignalData_Table.setRowCount(column_count)
           
            
            
           # self.ILA_ValuesTable.setColumnCount(self.ila_worker.table_range)
           # self.ILA_ValuesTable.setColumnCount(row_count)
            #self.ILA_ValuesTable.setRowCount(column_count)
            

    
            for row_index, (signal, data) in enumerate(df.items()):
                #signal_widget = QTableWidgetItem(str(signal))
                #self.ILA_SignalTable.setItem(row_index,0,signal_widget)
                for column_index, d in enumerate(data):
                    val = QTableWidgetItem(str(hex(int(d)))[2:])
                    val.setTextAlignment(Qt.AlignHCenter)
                    val.setTextAlignment(Qt.AlignVCenter)
                    self.ILASignalValue_Table.setItem(row_index, 0, val)
                    self.ILASignalData_Table.setItem(row_index, column_index, QTableWidgetItem(val))
                    
                color = self.getColor(row_index)
                self.setColortoRow(self.ILASignal_Table, row_index, color)
                self.setColortoRow(self.ILASignalValue_Table, row_index, color)
                self.setColortoRow(self.ILASignalData_Table,row_index, color)
                    
        except Exception as e:
            print(e)
            
    
    
    def sync_signal_scroll(self):
        signal_scrollbar_value = self.signalVerticalBar.value()
        self.valuesVerticalBar.setValue(signal_scrollbar_value)
    
    
    def sync_ila_data_scroll(self):
        ila_data_scrollbar_value = self.valuesVerticalBar.value()
        self.signalVerticalBar.setValue(ila_data_scrollbar_value)
        
    def setColortoRow(self, table, rowIndex, color):
        for j in range(table.columnCount()):
            table.item(rowIndex, j).setBackground(color)
            
    def getColor(self, col_index):
        if col_index % 2 == 0:
            color = QtGui.QColor("#d8d8d8")
        else:
            color = QtGui.QColor("#EAD2A8")
        
        return color 
                
                
    """
                for col_index, d in enumerate(data):
                    val = QTableWidgetItem(str(hex(int(d)))[2:])
                    val.setTextAlignment(Qt.AlignHCenter)
                    val.setTextAlignment(Qt.AlignVCenter)
                    #new_pos = self.ila_worker.table_range - row_count + col_index
                    #self.ILA_ValuesTable.setItem(row_index, new_pos, val)
                    self.ILASignalValue_Table.setItem(row_index, col_index, val)
                    self.ILASignalData_Table.setItem(row_index,1,QTableWidgetItem(val))
        
                color = self.getColor(row_index)
                self.setColortoRow(self.ILA_SignalTable, row_index, color)
                self.setColortoRow(self.ILA_ValuesTable, row_index, color)
    
            self.ILA_ValuesTable.verticalHeader().setVisible(False)
            self.ILA_SignalTable.setWordWrap(True)
            
            self.ILA_SignalTable.resizeColumnsToContents()
            
            
            self.ILA_TABS.setTabEnabled(1, True)
            
            
            self.signalVerticalBar = self.ILA_SignalTable.verticalScrollBar()
            self.valuesVerticalBar = self.ILA_ValuesTable.verticalScrollBar()
            
            self.signalVerticalBar.valueChanged.connect(self.sync_signal_scroll)
            self.valuesVerticalBar.valueChanged.connect(self.sync_ila_data_scroll)

        except Exception as error:
            show_error_message(f"{error}")
    """
    
    
    
            

    """
        # Remove widgets from the row
        for col in range(self.captureSetup_gridLayout.columnCount()):
            item = self.captureSetup_gridLayout.itemAtPosition(row_index, col)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()  # Delete the widget
                    
                    
        

        # Reorganize the layout
        for row in range(row_index + 1, self.grid_layout.rowCount()):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item:
                    self.grid_layout.addWidget(item.widget(), row - 1, col)
                    self.grid_layout.removeItem(item)

        # Adjust the row count of the grid layout
        self.grid_layout.setRowStretch(self.grid_layout.rowCount(), 0)

        # Update the visibility of captureSetup_Label
        self.captureSetup_Label.setVisible(self.grid_layout.rowCount() > 1)
    """

        
    

            
        
        
        
    """
    def create_ila_thread(self):
        self.ila_worker = ILA_Worker(selected_ila = self.selected_ila, main_window = self)
        
        self.ila_thread = QThread()
        self.ila_worker.moveToThread(self.ila_thread)
        
        self.ila_worker.dataframe_signal.connect(self.start_immediate_triggering)
        self.ila_worker.error.connect(self.display_ila_error)
        self.ila_worker.finished.connect(lambda: delete_thread_safely(window = self,
                                                                      worker_name = "ila_worker",
                                                                      thread_name = "ila_thread"))
        
        
        
        
        
        
    def trigger_checkbox_changed(self, state):
        sender = self.sender()
        
        
        
        if sender.isChecked() and sender.text() == "Basic Trigger":
            self.immediateTrigger_checkBox.setEnabled(False)
            self.triggeringSignals_ComboBox.setEnabled(True)
            
            self.trigger_mode = sender.text()
        

        elif sender.isChecked() and sender.text() == "Immediate Trigger":
            self.basicTrigger_checkBox.setEnabled(False)
            self.triggeringSignals_ComboBox.setEnabled(False)
            
            self.trigger_mode = sender.text()

        else:
            self.immediateTrigger_checkBox.setEnabled(True)
            self.basicTrigger_checkBox.setEnabled(True)
            self.triggeringSignals_ComboBox.setEnabled(True)
            
            self.trigger_mode = None
            
    def update_trigger_loop(self, state):
        sender = self.sender()

        
        if sender.isChecked() and sender.text() == "One-Time Trigger":
            self.continuousTrigger_checkBox.setEnabled(False)
            self.trigger_status = False
        
        elif sender.isChecked() and sender.text() == "Continuous Trigger":
            self.oneTimeTrigger_checkBox.setEnabled(False)
            self.trigger_status = True
            
        else:
            self.continuousTrigger_checkBox.setEnabled(True)
            self.oneTimeTrigger_checkBox.setEnabled(True)
            self.trigger_status = False
        
        
        
        
        
            
      
    def check_trigger_status(self):
        

        delete_thread_safely(window = self, worker_name = "ila_worker", thread_name = "ila_thread")
        
        
        #trigger_val = int(self.triggerValue_LineEdit.text(),16),
        if self.trigger_mode == "Immediate Trigger":
            self.create_ila_thread()
            self.ila_thread.started.connect(partial(self.ila_worker.immediate_trigger,
                                                    window_count = int(self.windowCount_lineEdit.text()),
                                                    buffer_size = int(self.bufferSize_lineEdit.text()),
                                                    trigger_pos = int(self.triggerPosition_lineEdit.text())))
            self.ila_thread.start()
            
        elif self.trigger_mode == "Basic Trigger":
            self.create_ila_thread()
            chosen_signal = self.triggeringSignals_ComboBox.currentText()[2:]
            self.ila_thread.started.connect(partial(self.ila_worker.basic_trigger,
                                                    signal = chosen_signal,
                                                    trigger_val = int(self.triggerValue_LineEdit.text(),16),
                                                    window_count = int(self.windowCount_lineEdit.text()),
                                                    buffer_size = int(self.bufferSize_lineEdit.text()),
                                                    trigger_pos = int(self.triggerPosition_lineEdit.text())))
            self.ila_thread.start()
            
        else:
            show_error_message("No Trigger mode has been set!")
            return
        
        show_informative_message("Ila Data Capturing Started! All data captured will be stored in local folder.")

        
   
        
    def stop_ila_thread(self):
        self.ila_worker.stop()
        show_informative_message("All ILA Data have been stored in the local folder"
                                 "- FINAL_ILA_DATASET.csv (testing purpose for now)")
        
        
    
    def display_ila_error(self, error):
        show_error_message(str(error))
        
    
    
        
    """
    
   
    
    def create_versal(self):

        if self.versal is None:
            self.versal = VersalSession(self)
            self.versal.connect()
            return
        self.versal.refresh_session()
        
                
            
    
    
    def connect_server(self):
        """
        Connect to the Device and display it's properties in the Main Menu
        """
        
        
        
        self.connection_Label.setText("Loading...")
        try:
            self.create_versal()
            self.scan_and_display_device_properties()
            self.connection_Label.setText("Successful connection to servers!")
            
            
        except Exception as e:
            self.connection_Label.setText("No servers connected yet!")
            show_error_message(f"Could not establish a connection with the device:\n{e}")
            return
        
       
        
        
        
    def scan_and_display_device_properties(self):
        
        try:
            self.update_session_status()
            self.update_device_id()
            self.update_programming_state()
            self.update_pdi_file()
            self.update_ltx_file()
            self.update_cables()
            self.display_ibert_core()
            self.display_pcie_core()
            self.display_ila_core()
        except AttributeError:
            show_error_message("Need to connect to the device first before refreshing properties!")
    
      
        
    def scanning_thread_finished(self):
        delete_thread_safely(window = self, worker_name = "scanning_worker", thread_name = "scanning_thread")
        self.stop_movie(self.mainMenu_Movie)
        
       
    @property
    def is_scanning_thread_alive(self):
        return self.scanning_worker is not None
    
    
    
            
    @pyqtSlot()
    def session_connection_lost(self):
        self.Session_TextBrowser.setText("Lost connection to device!")
        show_error_message("Lost connection with the device. Please try to connect again or restart application!")
            
    @pyqtSlot()
    def update_programming_state(self):
        self.ProgrammingStatus_TextBrowser.setText(str(self.versal.device.is_programmed))
        
    @pyqtSlot()
    def update_session_status(self): 
       
        self.Session_TextBrowser.setText(str(self.versal.device.chipscope_node))
        
    
    
    @pyqtSlot()   
    def update_device_id(self):
        self.deviceID_TextBrowser.setText(str(self.versal.device))

        # Check if self.versal.memory_targets is not None before iterating over it
        if self.versal.memory_targets is not None:
            # If not None, use it as usual
            self.MemoryTargets_TextBrowser.setText(", ".join(str(mem) for mem in self.versal.memory_targets))
            self.selectMemoryTarget_ComboBox.clear()
            self.selectMemoryTarget_ComboBox.addItems(self.versal.memory_targets)
        else:
            self.selectMemoryTarget_ComboBox.clear()
            
    @pyqtSlot()   
    def update_pdi_file(self):
        self.PDI_TextBrowser.setText(str(self.versal.pdi_file))
       
    @pyqtSlot()
    def update_ltx_file(self):
        
        self.LTX_TextBrowser.setText(str(self.versal.ltx_file))
    
    @pyqtSlot()
    def update_cables(self):
        self.Cables_TextBrowser.setText(str(self.versal.device.jtag_cable_node))
    
    @pyqtSlot()
    def display_ibert_core(self):
        if self.versal.ibert_core is not None:
            self.IbertCore_TextBrowser.setText(f"{self.versal.ibert_core}\n{', '.join(str(quad) for quad in self.versal.ibert_core.gt_groups)}")
            #self.display_ibert_hierarchy(treeView=self.ibertTreeView, gt_groups=self.versal.ibert_core.gt_groups)
        else:
            self.IbertCore_TextBrowser.setText(str(self.versal.ibert_core))
    
    @pyqtSlot()
    def display_pcie_core(self):
        self.PcieCore_TextBrowser.setText(str(self.versal.pcie_core))
    
    @pyqtSlot()
    def display_ila_core(self):
        if self.versal.ila_cores is not None:
            ila_cores_str = "\n".join(f"{index}: {str(ila)}" for index, ila in enumerate(self.versal.ila_cores))
            self.ILACore_TextBrowser.setText(ila_cores_str)
            #ila_cores_list = ila_cores_str.split('\n')
            #self.ILACores_ComboBox.clear()
            #self.ILACores_ComboBox.addItems(ila_cores_list)
        else:
            self.ILACores_ComboBox.clear()
            self.ILACore_TextBrowser.setText(str(self.versal.ila_cores))
            
        
        
        
     
    @pyqtSlot()
    def display_scanning_error(self, error_msg:str):
        show_error_message(error_msg)
            
    
    
    
    def clear_and_set_text(self, *args):
        """
        Clears and sets the text for the specified widgets.

        Args:
            *args: Variable-length argument list of tuples in the format (widget, text).
                - widget (QLineEdit, QLabel, QTextEdit, etc.): The widget to clear and set the text.
                - text (str): The text to set for the widget.

        Returns:
            None
        """
        for widget, text in args:
            widget.clear()
            widget.setText(text)         
    
    def retrieve_programming_files(self):
        """
        Retrieves the programming and probe files.

        This function retrieves the programming and probe files based on the path 
        specified in the design file line edit. The retrieved files are stored in 
        the class attributes `pdi_file` and `ltx_file`.

        Args:
            self (object): The current instance of the class.

        Returns:
            True -> if files are found 
            False -> if files are not found
        """
        
        try:
            
            self.versal.pdi_file = get_design_files(self.designFile_Line.text()).programming_file
            self.versal.ltx_file = get_design_files(self.designFile_Line.text()).probes_file
            return True
        except FileNotFoundError as f:
            print(self.designFile_Line.text())
            show_error_message(str(f))
    
    
    def clear_device_properties_frame(self):
        """
        Clears the device properties frame.

        This function clears and sets the text for the device properties frame, 
        including the device ID, memory targets, IBERT core, PCIe core, and ILA core. 
        The text is set to indicate that no information has been found yet.

        Args:
            self (object): The current instance of the class.

        Returns:
            None
        """
        self.clear_and_set_text((self.Session_TextBrowser,"No session set up yet..."),
                                (self.deviceID_TextBrowser,"No Device ID found yet..."),
                                (self.PDI_TextBrowser,"No PDI File found yet..."),
                                (self.LTX_TextBrowser,"No LTX File found yet..."),
                                (self.ProgrammingStatus_TextBrowser,"No Status Knowledge yet..."),
                                (self.Cables_TextBrowser,"No Cables found yet..."),
                                (self.MemoryTargets_TextBrowser,"No Memory Targets found yet..."),
                                (self.IbertCore_TextBrowser,"No IBERT Core found yet..."),
                                (self.PcieCore_TextBrowser,"No PCIe Core found yet..."),
                                (self.ILACore_TextBrowser,"No ILA Core found yet.."))
        print("Info: Finished clearing device properties")
        
    def program_device(self):
        """
        Initiates the programming of a device.

        This function performs the necessary steps to program a device. It verifies 
        the connection with the device, retrieves the programming and probe files, 
        clears the device properties frame, creates a programming worker object,
        establishes signal-slot connections for progress tracking and completion, 
        and starts the worker thread.

        Args:
            self (object): The current instance of the class.

        Returns:
            None
        """
        
        if self.versal is None:
            show_error_message("No connection has been established with a device!")
            return
        
        if not self.retrieve_programming_files():
            return
        
       
        
        self.programDesign_ProgressBar.setValue(0)
        self.programming_worker = ProgrammingWorker(versal = self.versal)

        programming_connections = {
        "progressChanged": [lambda progress: self.programDesign_ProgressBar.setValue(progress)],
        "error": [self.display_programming_error],
        "finished": [self.programming_finished]}
        
        programming_startup = [
            lambda: self.designProgrammed_Label.setText("Currently in programming process..."),
            lambda: self.programDesign_Button.setEnabled(False),
            lambda: self.clearAllMainMenu_Button.setEnabled(False),
            self.programming_worker.start_programming
        ]
        
        start_worker_thread(window = self, 
                            worker_name = "programming_worker", 
                            thread_name = "programming_thread",
                            connections = programming_connections,
                            execute_upon_startup = programming_startup)
       
    
  
    def programming_finished(self):
        """
        Handles the actions to be performed when the programming process is finished.

        This function is called when the programming process is completed successfully.
        It enables the program design button, updates the design programmed label with a success message,
        displays the device ID in the text browser, updates the memory targets, IBERT core, PCIe core, and
        ILA cores information, shows an informative message confirming successful programming and core scanning,
        enables the clear all main menu button, and safely deletes the programming thread.

        Returns:
            None
        """
        
        
        self.create_ibert_links()
        self.clear_treeView_Widget(treeView = self.ibertTreeView)
        self.display_ibert_hierarchy(treeView=self.ibertTreeView, gt_groups=self.versal.ibert_core.gt_groups)
        if self.versal.ila_cores is not None:
            ila_cores_str = "\n".join(f"{index + 1}: {str(ila)}" for index, ila in enumerate(self.versal.ila_cores))
            ila_cores_list = ila_cores_str.split('\n')
            self.ILACores_ComboBox.clear()
            self.ILACores_ComboBox.addItems(ila_cores_list)
        
        self.programDesign_Button.setEnabled(True),
        self.designProgrammed_Label.setText("Successfully programmed design!"),
        show_informative_message("Programmed succesfully and scanned all cores for this programmed design"),
        self.clearAllMainMenu_Button.setEnabled(True),
        delete_thread_safely(window=self, worker_name="programming_worker", thread_name="programming_thread") 
        self.scan_and_display_device_properties()
        

    
    def display_ibert_hierarchy(self, treeView, gt_groups):
        """
        Display the IBERT hierarchy in the given treeView widget based on the provided gt_groups.

        Args:
            treeView: QTreeView widget to display the hierarchy
            gt_groups: List of gt_groups representing the hierarchy
        """
        
        if gt_groups:
            model = QStandardItemModel()
            root_item = model.invisibleRootItem()

            for i, quad in enumerate(gt_groups):
                quad_item = QStandardItem(str(quad))
                root_item.appendRow(quad_item)
                for child in quad.children:
                    child_item = QStandardItem(str(child))
                    quad_item.appendRow(child_item)
                    if child in quad.gts:
                        child_item.appendRow(QStandardItem("TX"))
                        child_item.appendRow(QStandardItem("RX"))

            # Set the model to the existing ibertTreeView
            treeView.setModel(model)
            treeView.setHeaderHidden(True)
        
     

    def display_programming_error(self, error):
        """
        Displays error message if programming a design to the
        Versal Device is unsuccessful. This function is linked
        with the "error" signal of ProgrammingWorker Class
        
        Once error is displayed to the user, the worker thread
        is than stopped and deleted.
        
        Args:
            error(str): The error message emitted from the 
                        programming worker if programming
                        device was not successful
        Returns:
            None
        """
        show_error_message(str(error))
        self.designProgrammed_Label.setText(str(error))
        self.programDesign_Button.setEnabled(True)
        delete_thread_safely(window = self, worker_name = "programming_worker", 
                             thread_name = "programming_thread")
        self.clearAllMainMenu_Button.setEnabled(True)
        self.programDesign_ProgressBar.setValue(0)
        
    
    
        
    
    def start_ltssm_thread(self):
        """
        If PCIe Core is detected, creates and starts a LTSSM Worker Thread.
        
        Returns:
            None
        """
        if self.versal is None:
            show_error_message("No connection establish with the Device!")
            return
        
        if self.versal.pcie_core is None:
            show_error_message(f"No PCIe Core available in the current programmed design:\n{self.pdi_file}\n{self.ltx_file}")
            return
        
        self.ltssm_worker = LTSSM_Worker(self.versal)
        
        ltssm_connections = {
            "error": [self.display_ltssm_error],
            "finished": [
                lambda:self.displayLTSSM_Button.setEnabled(True),
                self.change_ltssm_status_icon,
                lambda: delete_thread_safely(window = self, worker_name = "ltssm_worker",thread_name = "ltssm_thread")
            ],
            "ltssm_img": [self.display_and_refresh_ltssm]
        }
        
        
        start_worker_thread(window = self,
                            worker_name = "ltssm_worker",
                            thread_name = "ltssm_thread",
                            connections = ltssm_connections,
                            execute_upon_startup = [
                                self.change_ltssm_status_icon,
                                lambda: self.displayLTSSM_Button.setEnabled(False),
                                lambda: show_informative_message("Started scanning LTSSM Graph in Real-Time"),
                                self.ltssm_worker.scan_ltssm_graph
                            ])
        
        
    def change_ltssm_status_icon(self):
        """
        Toggles the LTSSM status icon between two images.

        This function is called to toggle the LTSSM status icon between two different images.
        It switches the stylesheet of the `ltssmStatus_Label` based on the current state.

        Returns:
            None
        """
        current_stylesheet = self.ltssmStatus_Label.styleSheet()

        if current_stylesheet.endswith("stop_read_icon.png);"):
            self.ltssmStatus_Label.setStyleSheet("image: url(:/logos/green_status.png);")
        else:
            self.ltssmStatus_Label.setStyleSheet("image: url(:/logos/stop_read_icon.png);")
        
    
    def display_ltssm_error(self, error):
        show_error_message(str(error))
        
        
    def display_and_refresh_ltssm(self, ltssm_plt):
        """
        Displays and refreshes the LTSSM image in the UI.

        This function updates the LTSSM image in the UI based on the provided ltssm_plt.
        It removes any previous LTSSM labels from the ltssmGraph_Area, creates a new QLabel
        with the updated image, and adds it to the layout of ltssmGraph_Area.
        
        Ultimately, this function updates the LTSSM Plot in Real-Time

        Args:
            ltssm_plt: The LTSSM image to display and refresh.

        Returns:
            None
        """

        if self.ltssmGraph_Area.layout() is None:
            self.ltssmGraph_Area.setLayout(QVBoxLayout())

        while self.ltssmGraph_Area.layout().count() > 0:
            item = self.ltssmGraph_Area.layout().takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        
        ltssm_label = QLabel(self.ltssmGraph_Area)
        ltssm_pixmap = QPixmap.fromImage(ltssm_plt)
        ltssm_label.setPixmap(ltssm_pixmap)
        ltssm_label.setScaledContents(True)
        self.ltssmGraph_Area.layout().addWidget(ltssm_label)
        
        """
        
        # print("Starting DISPLAY_AND_REFRESH_LTSSM Function")
        if self.ltssmGraph_Area.layout() is None:
            self.ltssmGraph_Area.setLayout(QVBoxLayout())

        if hasattr(self, 'ltssm_label'):
            self.ltssmGraph_Area.layout().removeWidget(self.ltssm_label)
            self.ltssm_label.deleteLater()

        ltssm_label = QLabel(self.ltssmGraph_Area)
        ltssm_pixmap = QPixmap.fromImage(ltssm_plt.toImage())
        ltssm_label.setPixmap(ltssm_pixmap)
        ltssm_label.setScaledContents(True)
        ltssm_label.setAlignment(QtCore.Qt.AlignCenter)

        self.ltssmGraph_Area.layout().addWidget(ltssm_label)
        self.ltssm_label = ltssm_label
        """
    
    def stop_ltssm_thread(self):
        """
        Stops the LTSSM thread if it is currently running.

        This function checks if the LTSSM thread is currently running. If the thread is running,
        it calls the `stop()` method on the `ltssm_worker` object to stop the LTSSM scanning process.
        If the LTSSM thread is not running, an error message is displayed.

        """
        
        if self.ltssm_worker is None:
            show_error_message("No Scanning is being processed at the moment!")
            return
        
        self.ltssm_worker.stop()
        
    def delete_ltssm_thread_upon_app_exit(self):
        if self.ltssm_worker:
            self.ltssm_worker.stop()
        
        
            
    def reset_pcie_core(self):
        """
        If PCIe Core is detected, it will reset it.
        
        Returns:
            None
        """
        if self.versal is None:
            show_error_message("No connection is established with device!")
            return
            
        if self.versal.pcie_core is None:
            show_error_message("No PCIe Core has been detected!")
            return
        
        self.versal.pcie_core.reset_core()
        show_informative_message("Successfuly reset PCIe Core!")
        
     
        
    def initiate_realtime_register_reading(self):
        """
        Start real-time register reading process.
        
        Checks if a session connection has been established with the Versal Device.
        Checks if any registers are inputted for reading.
        
        If the above conditions pass, register addresses, memory targets and read size
        are retrieved from the UI Elements.
        
        A worker thread is created for processing memory reads and sends signals back to
        main thread that carry the data from these registers, which are displayed in the QTableWidget
        
        Key variables created inside this functin:
            "RegisterWorker" (object): the worker thread that will process real-time memory reads
            "npi_signal_connections" (dict): the connections for the worker thread 
            "startup_events" (list): the events that will happen when worker thread starts
        
        Returns:
            None
        """
        
        
        if self.versal is None:
            QMessageBox.information(None,"Error","No session is established with the device!")
            return
        
        if self.is_text_edit_empty(self.readRegister_Text):
            show_informative_message("No registers inputted for reading!")
            return
        
        
        if (self.record_register_data_radioButton.isChecked() and 
            self.is_text_edit_empty(self.registerRecords_LineEdit)):
            show_informative_message("Please input a filename where the register values will be stored!")
            return
        
        
        
        
        self.REG_ADDRESSES = self.parse_input_to_hex(self.readRegister_Text.toPlainText())
        self.MEMORY_TARGET = self.selectMemoryTarget_ComboBox.currentText()
        self.READ_SIZE = self.selectSize_ComboBox.currentText()[0]
        
        
        
        self.adjust_table_rows_for_registers(self.REG_ADDRESSES, self.RegisterResult_Table)
        
        
        record_file_str = self.registerRecords_LineEdit.text()
        
        if self.record_register_data_radioButton.isChecked():
        
            self.RegisterWorker = RegisterReadWorker(self.versal,
                                                    self.REG_ADDRESSES, 
                                                    self.MEMORY_TARGET, 
                                                    self.READ_SIZE,
                                                    record_file_str)
            npi_signal_connections = {
                "readFinished": [self.display_register_data],
                "html_file":[self.update_register_records_html_file],
                "error": [self.display_read_error],
                "finished":[self.realtime_register_reading_finished]
            }
        else:
            self.registerRecords_LineEdit.clear()
            self.RegisterWorker = RegisterReadWorker(self.versal,
                                                    self.REG_ADDRESSES, 
                                                    self.MEMORY_TARGET, 
                                                    self.READ_SIZE,
                                                    records_file = None)
            npi_signal_connections = {
                "readFinished": [self.display_register_data],
                "error": [self.display_read_error],
                "finished":[self.realtime_register_reading_finished_without_background_storage]
            }
            
        
        startup_events = [
            lambda: self.startReading_Button.setEnabled(False),
            lambda: self.readingStatus_Label.setText("Register Thread is scanning..."),
            lambda: show_informative_message("Real-Time register reading started!"),
            lambda: self.RegisterResult_Table.clearContents(),
            self.RegisterWorker.start_reading
        ]
        
        
        start_worker_thread(window = self,
                            worker_name = "RegisterWorker",
                            thread_name = "RegisterThread",
                            connections = npi_signal_connections,
                            execute_upon_startup = startup_events)
        
        self.registerLoading_Movie = self.set_movie_for_label(self.registerLoadingLabel, "GUI_Logos/loading_movie.gif")
        
        
    
    def realtime_register_reading_finished(self):
        
        if not self.RegisterWorker.READ_ERROR:
            show_informative_message(f"Reading has stopped. Register values stored in:\n{self.RegisterWorker.filename_csv}\n{self.RegisterWorker.filename_html} !")
        
        
        
        delete_thread_safely(window = self, worker_name = "RegisterWorker", thread_name = "RegisterThread")
        self.startReading_Button.setEnabled(True)
        self.readingStatus_Label.setText("Reading registers scan stopped")
        self.registerLoading_Movie = self.set_movie_for_label(self.registerLoadingLabel, "GUI_Logos/red_icon_for_ltssm.png")
        self.stop_movie(self.registerLoading_Movie)
        
    
    def realtime_register_reading_finished_without_background_storage(self):
        delete_thread_safely(window = self, worker_name = "RegisterWorker", thread_name = "RegisterThread")
        self.startReading_Button.setEnabled(True)
        self.readingStatus_Label.setText("Reading registers scan stopped")
        self.registerLoading_Movie = self.set_movie_for_label(self.registerLoadingLabel, "GUI_Logos/red_icon_for_ltssm.png")
        self.stop_movie(self.registerLoading_Movie)
        show_informative_message("Reading registers has stopped!")
    
    def realtime_register_reading_finished_app_closing(self):
        if self.RegisterWorker:
            delete_thread_safely(window = self, worker_name = "RegisterWorker", thread_name = "RegisterThread")
    
    

    @pyqtSlot(str)
    def update_register_records_html_file(self, filepath):
        self.register_worker_records_html = filepath
        
    
    def extract_phyrdy_register(self):
        phyrdy_register = "0xFCA50E90"
        self.readRegister_Text.append(phyrdy_register)
        
    def extract_gt_reset_fsm_register(self):
        gt_reset_fsm_registers = ["0xF72121D8","0xF72125D8","0xF72129D8","0xF7212DD8"]
        for register in gt_reset_fsm_registers:
            self.readRegister_Text.append(register)
            
    def extract_ltssm_register(self):
        ltssm_registers = ["0xF721200C","0xF721240C","0xF721280C","0xF7212C0C"]
        for register in ltssm_registers:
            self.readRegister_Text.append(register)
        
    
    def adjust_table_rows_for_registers(self, registers: list, table_widget: object):
        """
        Adjusts the number of rows in the table widget based on its height and the number of registers.

        This method calculates the number of rows based on the height of the table widget's visible area and the height
        of a single row. It ensures that the table widget has enough rows to display content within its visible area,
        considering the number of registers that will be displayed.

        Args:
            registers (list): A list of registers that will be inputted in the table.
            table_widget (QTableWidget): The table widget to adjust the row count for.

        Returns:
            None
        """
        row_height = table_widget.rowHeight(0)  
        viewport_height = table_widget.viewport().height()  
        num_rows = viewport_height // row_height
        table_widget.setRowCount(max(num_rows, len(registers)))
            
        
    
    
    def is_text_edit_empty(self, text_edit):
        """
        Checks if a QTextEdit widget is empty.

        This function retrieves the text from the QTextEdit widget or QLineEdit using the `toPlainText()`
        or 'text()' method and checks if the resulting string is empty.

        Args:
            text_edit (QTextEdit or QLineEdit): The QTextEdit widget to check.

        Returns:
            bool: True if the QTextEdit is empty, False otherwise.
        """
        try:
            text = text_edit.toPlainText()
        except AttributeError:
            text = text_edit.text()
        
        return len(text.strip()) == 0
    
    def display_register_data(self, register_data:[]):
        """
        Displays register data in the table.

        Populates the RegisterResult_Table with register data provided as a list 
        containing address, hex value, and binary value. The table columns are aligned 
        and resized after populating the data.

        Args:
            register_data (list): List of tuples containing register data.

        Returns:
            None
        """
        

        for row, data in enumerate(register_data):

            address, hex_val, bin_val = data

            address_item = QTableWidgetItem(str(address))
            address_item.setTextAlignment(Qt.AlignCenter)
            hex_val_item = QTableWidgetItem(hex_val)
            hex_val_item.setTextAlignment(Qt.AlignCenter)
            bin_val_item = QTableWidgetItem(bin_val)
            bin_val_item.setTextAlignment(Qt.AlignCenter)

            self.RegisterResult_Table.setItem(row, 0, address_item)
            self.RegisterResult_Table.setItem(row, 1, hex_val_item)
            self.RegisterResult_Table.setItem(row, 2, bin_val_item)

        self.RegisterResult_Table.resizeColumnsToContents()
        
    
            

    def open_register_records_file(self):
        if self.register_worker_records_html is None:
            show_informative_message("No records have been made recently or there might have been an error reading!")
            return
        
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.register_worker_records_html))
        
    def open_register_debugging_article(self):
        QDesktopServices.openUrl(QUrl("https://support.xilinx.com/s/article/1221922?language=en_US"))
        
        
    def stop_realtime_register_reading(self):
        
        if self.versal is None:
            show_informative_message("No connection has been established yet!")
            return
        
        if self.RegisterWorker is None:
            show_informative_message("Reading Registers has already been stopped or hasn't started yet!")
            return
       
        self.RegisterWorker.stop()
            
        
        
    def display_read_error(self, error):
        show_error_message(str(error))
        
           
            
    def write_to_registers(self):
        
        writeValues = self.parse_input_to_hex(self.writeRegister_Text.text())
        
        if len(writeValues) == 0:
            QMessageBox.information(None,"Information","No values entered for writing!")
            return
        
        for address in self.REG_ADDRESSES:
            self.versal.device.memory_write(address = address, 
                                            values = writeValues, 
                                            size = self.READ_SIZE, 
                                            target = self.MEMORY_TARGET)
        
    
        
    def stop_ibert_thread(self):
        if self.ibert_thread.is_alive():
            self.ibert_worker.stop()
    
    def ibert_thread_finished(self):
        print("ibert thread finished!!!")
        #[progress_bar.setValue(100) for progress_bar in self.eye_progress_bars]
        
        
    
    def clear_treeView_Widget(self, treeView):
        try:
            tree_model = treeView.model()
            tree_model.clear()
        except:
            pass

    
    
    
    def create_ibert_links(self):
        delete_links(self.versal.ibert_links)
        delete_eye_scans(self.versal.eye_scans)
       
        transceivers = []
        receivers = []
        # Collect transceivers and receivers
        for n, quad in enumerate(self.versal.ibert_core.gt_groups):
            transceivers.append(quad.gts[n].tx)
            receivers.append(quad.gts[n].rx)
        self.versal.ibert_links= create_links(txs=transceivers, rxs=receivers)
        
        if self.versal.ibert_links:
            for i, link in enumerate(self.versal.ibert_links):
                tx_pattern_report = link.tx.property.report(link.tx.property_for_alias[PATTERN]).popitem()
                rx_pattern_report = link.rx.property.report(link.rx.property_for_alias[PATTERN]).popitem()
                rx_loopback_report = link.tx.property.report(link.rx.property_for_alias[RX_LOOPBACK]).popitem()

                # Extract the valid values from the reports
                tx_valid_values = tx_pattern_report[1]['Valid values']
                rx_valid_values = rx_pattern_report[1]['Valid values']
                rx_loopback_valid_values = rx_loopback_report[1]['Valid values']
                #self.widget_link_properties.emit([i, tx_valid_values, rx_valid_values, rx_loopback_valid_values])
                self.fill_link_properties_box(i, tx_valid_values, rx_valid_values, rx_loopback_valid_values)
                
        
         
        self.versal.eye_scans = create_eye_scans(target_objs=[link for link in self.versal.ibert_links]) 
    
    
    
    def fill_link_properties_box(self, index, tx_valid_values, rx_valid_values, rx_loopback_valid_values):
        
        
        
        
        # combo boxes
        link_label = QLabel(f"Link {index + 1}")
        tx_label = QLabel("TX Properties: ")
        tx_combo = QComboBox()
        tx_combo.addItems(tx_valid_values)
        
        
        rx_label = QLabel("RX Properties: ")
        rx_combo = QComboBox()
        rx_combo.addItems(rx_valid_values)
        
       
        loopback_label = QLabel("Loopback Properties:")
        loopback_combo = QComboBox()
        loopback_combo.addItems(rx_loopback_valid_values)
        
        self.combo_boxes.append([tx_combo,rx_combo,loopback_combo])
        
        link_layout = QHBoxLayout()
        link_layout.addWidget(link_label)
        link_layout.addWidget(tx_label)
        link_layout.addWidget(tx_combo)
        link_layout.addWidget(rx_label)
        link_layout.addWidget(rx_combo)
        link_layout.addWidget(loopback_label)
        link_layout.addWidget(loopback_combo)

        
        
        self.linkPropertiesWidgets.extend([link_label, tx_label, tx_combo, 
                                           rx_label, rx_combo, loopback_label,
                                           loopback_combo, link_layout])
        
        self.combined_link_layout.addLayout(link_layout)
        self.linkPropertiesGroupBox.setLayout(self.combined_link_layout)
        
        # Progress bars
        layout = QGridLayout()
        progress_bar = QProgressBar()
        progress_bar.setValue(0)
        eye_scan_label = QLabel(f"Eye Scan {index + 1}")
        eye_scan_status_label = QLabel("Not started yet!")
        
       
        layout.addWidget(eye_scan_label, index, 0)
        layout.addWidget(progress_bar, index, 1)
        layout.addWidget(eye_scan_status_label, index, 2)
        self.eye_progress_bars.append(progress_bar)
        
        self.eye_progress_bars_layout.addRow(layout)
        self.eyeScanProgressGroupBox.setLayout(self.eye_progress_bars_layout)
        self.linkPropertiesWidgets.extend([eye_scan_label, progress_bar, eye_scan_status_label, layout])
        self.eyeScanStatus_Labels_Layout_ls.append(eye_scan_status_label)
        
        
        
    def set_link_properties(self):
       # if self.ibert_worker is None:
           # show_error_message("No IBERT setup!")
           # return
        
        
        
        if self.versal.ibert_links is None:
            show_error_message("No IBERT Setup!")
            return
        
        try:
            for i, link in enumerate(self.versal.ibert_links):
                tx_value = self.combo_boxes[i][0].currentText()
                rx_value = self.combo_boxes[i][1].currentText()
                loopback_value = self.combo_boxes[i][2].currentText()

                props = {
                    link.tx.property_for_alias[PATTERN]: tx_value,
                    link.rx.property_for_alias[PATTERN]: rx_value,
                    link.rx.property_for_alias[RX_LOOPBACK]: loopback_value,
                }

                link.tx.property.set(**props)
                link.tx.property.commit(list(props.keys()))
            QMessageBox.information(None, "Information", "Set Link Properties Successfully!")
        except Exception as e:
            show_error_message(str(e))
            return
        
        
       

    
    def start_eye_scans(self):
        
        
        if self.versal.ibert_links is None:
            show_error_message("No IBERT Setup!")
            return
        
      
        
        
        self.ibert_worker = IbertWorker(self.versal, self)
        
        ibert_connections = {
            "eye_progress": [self.update_eye_scan_bars],
            "eye_scan_picture": [self.plot_eye_scans],
            "eye_scan_status": [self.update_eye_scan_status],
            "finished": [self.ibert_thread_finished]
        }
        
        
        
        
        
        start_worker_thread(window = self,
                            worker_name = "ibert_worker",
                            thread_name = "ibert_thread",
                            connections = ibert_connections,
                            execute_upon_startup = [self.ibert_worker.start_eye_scans])

        
        
    def stop_ibert_threads(self):
        
        if len(self.ibert_worker_objects) != 0:
            for worker in self.ibert_worker_objects:
                worker.stop()
            
        
     
        
    @pyqtSlot(list)
    def update_eye_scan_bars(self, progress_info):
        index, progress = progress_info
        self.eye_progress_bars[index].setValue(progress)
        
    
    
    @pyqtSlot(int, str)
    def update_eye_scan_status(self,index:int, status:str):
        
        if self.eyeScanStatus_Labels_Layout_ls:
            self.eyeScanStatus_Labels_Layout_ls[index].setText(status)
        
    
        
    
    def plot_eye_scans(self, data):
        
        
        try:
            index, scan = data
        
            
                
            tab = QWidget()
            tab.setObjectName(f"eyeScanTab_{index+1}")
            layout = QVBoxLayout(tab)
            plot_png = scan.plot.save(file_format="PNG")
            image = QPixmap(plot_png)
            label = QLabel(tab)
            label.setPixmap(image)
            label.setScaledContents(True)
            label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(label)
            self.ibertPlottingTab.addTab(tab, f"Eye Scan {index+1}")
            self.eye_scan_tabs.append(tab)
            
        except Exception as e:
            print(e)
            
            
    def clear_all_settings_to_default(self):
        
        
        if not self.versal.is_device_available:
            show_informative_message("No Device available to reset!")
            return
            
        if not self.versal.is_session_available:
            show_informative_message("No Session available to reset!")
            return
            
        self.clear_device_properties_frame()
        
        
            
            
        
        
        
        self.programDesign_ProgressBar.setValue(0)
        self.versal.device.reset()
        self.versal.delete_current_session()
        
        self.connection_Label.setText("Cleared settings to default!")
        self.designProgrammed_Label.setText("Device was reset to default!")
        
        for i, widget in enumerate(self.linkPropertiesWidgets):
            widget.deleteLater()
        self.linkPropertiesWidgets = []
        self.combo_boxes = []
        
        if self.ibertPlottingTab.count() > 1:
            for index in range(self.ibertPlottingTab.count() - 1, 0, -1):
                self.ibertPlottingTab.removeTab(index)
                
        #self.ibert_worker.eye_scans_length = None
        
        self.ILACores_ComboBox.clear()
        #self.triggeringSignals_ComboBox.clear()
        self.ILA_TABS.setTabEnabled(1,False)
        
        
        
        self.clear_treeView_Widget(treeView = self.ibertTreeView)

        
        
        delete_thread_safely(window = self,
                             worker_name = "programming_worker",
                             thread_name = "programming_thread"
                            )
        
        delete_thread_safely(window = self,
                             worker_name = "RegisterWorker",
                             thread_name = "RegisterThread"
                             )
        
        delete_thread_safely(window = self,
                             worker_name = "ibert_worker",
                             thread_name = "ibert_thread"
                            )
        
        delete_thread_safely(window = self,
                             worker_name = "ltssm_worker",
                             thread_name = "ltssm_thread"
                            )
        
        
        self.versal.initialize_attributes()
        self.eyeScanStatus_Labels_Layout_ls = []
        self.eye_progress_bars = []
        self.versal = None
        
        QMessageBox.information(None,"Information","Reset All Settings to Default")

        
    def clear_reading_registers(self):
        """
        Clear the reading registers.

        This method clears the text in the readRegisterText field and clears the contents of the RegisterResultTable.
        """
        
        if hasattr(self,"RegisterThread"):
            if self.RegisterThread is None:
                self.readRegister_Text.clear()
                self.RegisterResult_Table.clearContents()
            elif self.RegisterThread.isRunning():
                show_error_message("Register Reading is under process. Please stop reading to clear!")
                return
            
        


        
            
    def extract_csv_file(self):
        """
        Extract a file and process its contents.

        This method allows the user to select a file using a file dialog. Once a file is selected, it checks the file extension and processes the contents accordingly. If the file is a CSV file, it searches for a column containing register addresses and extracts those addresses to populate the readRegisterText field.
        """
        #self.extractedCsvFile_LineEdit.clear()

        
        #filePath =  browse_file(window = self)
        # Open file dialog with white background
        fileDialog = QFileDialog(self)
        fileDialog.setStyleSheet("QFileDialog { background-color: white; }")
        filePath, _ = fileDialog.getOpenFileName(self, "Open CSV File", "", "CSV Files (*.csv);;All Files (*)")

        if not filePath or not filePath.endswith(".csv"):
            show_error_message("File selected was not a csv file!")
            return
        
        self.extractedCsvFile_LineEdit.clear()
        self.extractedCsvFile_LineEdit.setText(filePath)
        self.npi_csv_df = pd.read_csv(filePath)
        
    
    def extract_registers_from_csv(self):
        try:
            reg_col = self.RegColumnHeader_LineEdit.text()
            if reg_col.lower() not in map(str.lower, self.npi_csv_df.columns):
                show_error_message(f"{reg_col} not part of any column header")
                return

            for n,addr in enumerate(self.npi_csv_df[reg_col].to_list()):
                address = self.extract_address(addr)
                if address is not None and self.is_hex(address):
                    self.readRegister_Text.append(address)
        except KeyError as k:
            show_error_message(f"Could not find header '{k}'")

 
    def is_hex(self, s: str):
        try:
            int(s, 16)
            return True
        except ValueError:
            return False

    def extract_address(self, address):
        """
        Extract the address from a string.

        This method takes an input string and extracts the register address from it. 
        It uses regular expressions to search for hexadecimal address patterns. 
        If a valid address is found, it returns the address as a hexadecimal string. 
        Otherwise, it returns None.

        Args:
            address (str): The input string containing the register address.

        Returns:
            str or None: The extracted register address as a hexadecimal string, or None if no valid address is found.
        """
        try:
            pattern = re.search(r'0[xX][0-9a-fA-F]+', str(address))
            if pattern is not None:
                hex_string = pattern.string
                hex_string = hex_string.replace("[", "").replace("]", "").replace(" ", "")
                return str(hex_string)
        except ValueError:
            pass
        
        
    def parse_input_to_hex(self, input_str: str) -> List[int]:
        """
        Parse hexadecimal input string and return a list of integers

        The input string can be separated by commas or whitespace.
        """
        try:
            hex_vals = re.split(r',\s*|\s+', input_str)
            return [int(val, 16) for val in hex_vals if val.strip()]
        except ValueError:
            pass

    def switch_section_page(self, index):
        self.stackedWidget.setCurrentIndex(index)

    def update_label(self, label: QLabel, text: str) -> None:
        """
        Updates label with new Font and Text
        """
        self.set_font(label)
        label.setText(text)
        

    def set_font(self, label: QLabel) -> None:
        """
        Updates label with Italic font
        """
        font = QtGui.QFont("Segoe Print")
        font.setItalic(True)
        font.setPointSize(13)
        label.setFont(font)
        



os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())


# In[ ]:





