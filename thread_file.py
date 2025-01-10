# Copyright (C) 2024, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT


from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
import pandas as pd
import numpy as np
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QThread, QMutex, QMutexLocker, QWaitCondition
from chipscopy.api.ibert import create_eye_scans, create_links, delete_eye_scans, get_all_links, get_all_eye_scans
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
from chipscopy.api.ibert import create_eye_scans, create_links, delete_eye_scans, delete_links
from chipscopy.api.ila import ILAStatus, ILAState, export_waveform
from chipscopy import get_examples_dir_or_die, null_callback, delete_session
import os
import time
import sys 
import io
import csv
from datetime import datetime

class ProgrammingWorker(QObject):
    """
    Worker class for programming a device.

    This class handles the programming process of a device using a PDI file and
    LTX file for discovering cores.

    Signals:
        progressChanged: Signal emitted with the progress percentage during programming.
        finished: Signal emitted when programming is completed.
        error: Signal emitted when an error occurs during programming.

    Args:
        versal (object): The VersalSession instance.
        pdi_file (str): The PDI file to use for programming.
        probes_file (str): The LTX File to use for discovering cores.
    """
    progressChanged = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, versal):
        """
        Initialize the ProgrammingWorker.
        
        
        Args:
            versal (object): The Device instance to program.
            pdi_file (str): The PDI file to use for programming.
            probes_file (str): The LTX File to use for discovering cores
        """
        super().__init__()         
        self.versal = versal
        

    def start_programming(self):
        """
        Start the programming process.

        This method triggers the programming process of the device by calling the `program`
        and `discover_cores` methods. It emits the progressChanged signal with the progress
        percentage during programming and the finished signal when programming is completed.
        If an error occurs during programming, it emits the error signal.
        
        Raises:
            Exception: If an error occurs during programming, it is caught and emitted through the error signal.
        """
        def update_progress(progress: float):
            """
            Update the progress during programming.

            Args:
                progress (float): The progress value ranging from 0.0 to 1.0.
            """
            progress_percentage = int(progress * 100)
            self.progressChanged.emit(progress_percentage)
    
        try:
            self.versal.device.program(programming_file = self.versal.pdi_file, 
                                       progress = update_progress,
                                       show_progress_bar=False)
            self.versal.discover_cores()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
            
            
class RegisterReadWorker(QObject):
    """
    Worker class for reading memory registers.

    This class handles the process of reading memory registers of a device
    and storing the values in a register record.

    Signals:
        readFinished: Signal emitted with the register data (address-value pairs) after reading is completed.
        finished: Signal emitted when the reading process iscompleted.
        error: Signal emitted when an error occurs during the reading process.

    Args:
        REGISTER_RECORDS (dict): Dictionary to store the register records.
        versal (object): The VersalSession instance 
        register_addresses (list): List of memory addresses to read.
        memory_target (str): The memory target to read from.
        read_size (str): The size of the read operation.
    """
    
    readFinished = pyqtSignal(list)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    html_file = pyqtSignal(str)

    def __init__(self, versal, register_addresses, memory_target, read_size, records_file):
        """
        Initialize the RegisterReadWorker.

        Args:
            device: The device instance to read from.
            register_addresses (list): List of memory addresses to read.
            memory_target (str): The memory target to read from.
            read_size (str): The size of the read operation.
        """
        super().__init__()

        self.REGISTER_RECORDS = {}
        self.versal = versal
        self.register_addresses = register_addresses
        self.memory_target = memory_target
        self.read_size = read_size
        self.records_file = records_file
        self.READ_STATUS = True
        self.READ_ERROR = False
        
        
        
        self.filename_csv = str(self.records_file)
        if ".csv" not in self.filename_csv:
            self.filename_csv = self.filename_csv + ".csv"
            
        self.filename_html = self.filename_csv.replace(".csv",".html")
        
    def start_reading(self):
        """
        Start reading the specified memory addresses.

        This method initiates the process of reading the memory addresses specified 
        in `register_addresses`. It retrieves the hexadecimal values from the memory 
        addresses using the `read_and_parse` method. The retrieved values are then 
        checked and stored in the `REGISTER_RECORDS` attribute using the `check_register_records` method. 
        The register data, consisting of address-value pairs, is collected in a list and emitted through 
        the `readFinished` signal.

        Raises:
            Exception: If an error occurs during the reading process, it is caught and 
            emitted through the `error` signal.

        """
        print("STARTED THREAD")

        while self.READ_STATUS:
            try:
                register_data = []
                for address in self.register_addresses:
                    hex_val, bin_val = self.read_and_parse(address)
                    
                    self.check_register_records(address, hex_val)
        
                    register_data.append([hex(address), hex_val, bin_val])

                self.readFinished.emit(register_data)

            except Exception as e:
                self.READ_ERROR = True
                self.error.emit(str(e))
                self.stop()
            QThread.msleep(20)
                
    

    def read_and_parse(self, addr: int):
        """
        Retrieve the value from the specified address.

        Args:
            addr (int): The memory address to read from.

        Returns:
            tuple: A tuple containing the hexadecimal value and binary value retrieved from the address.
        """
        
        bit_size = {"b": 8, "h": 16, "w": 32}
        key = str(self.read_size)

        value = self.versal.device.memory_read(address = addr, 
                                               size = self.read_size, 
                                               target = self.memory_target)[0]

        bin_value = f"{value:0{bit_size[key]}b}"
        hex_format = f"0x{value:0{bit_size[key] // 4}x}"
        return [hex_format, bin_value]

        
            
            
    def check_register_records(self, address, values):
        """
        Check and update the register records dictionary with the given address and values.

        Args:
            address: The address to check and update.
            values: The values to append to the address entry in the register records.

        """
        
        if address not in self.REGISTER_RECORDS:
            self.REGISTER_RECORDS[address] = []
        
        

        # Extract the values from the stored tuples and compare only the values
        stored_values = [value[0] for value in self.REGISTER_RECORDS[address]]

        if values not in stored_values:
            time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            value_with_time = (values, time)
            self.REGISTER_RECORDS[address].append(value_with_time)   

        
            
       

    
    def store_records_to_file(self):
        """
        Store the register records to a file.

        This method saves the register records stored in the `REGISTER_RECORDS` attribute 
        to a CSV file and an HTML file. The CSV file contains the raw data, while the HTML 
        file provides a stylized and formatted representation of the data. The HTML file includes 
        styling, such as highlighting specific columns and setting font sizes.

        Raises:
            Exception: If an error occurs while writing the records to the files, it is caught and printed.

        """
        
        
        
        def highlight_col(row):
            """
            Applying color to entire rows based on condition
            """
            if "0x" in row["Address"]:
                return ["background-color: #C0C0C0"] * len(row)
            else:
                return ["background-color:#F9E9D0"] * len(row)
        

        try:
            # Create a DataFrame from the register records
            data = []
            dec_ls = []
            bit_ls = []
            time_ls = []
            
            for address, values in self.REGISTER_RECORDS.items():
                dec_ls.append(np.nan)
                bit_ls.append(np.nan)
                time_ls.append(np.nan)
                data.append({'Address': hex(address)})
                for value, time in values:
                    data.append({'Value(Hex)': value})
                    
                    
                    dec_ls.append(str(int(value,16)))
                    time_ls.append(time)
                    
                    if len(bin(int(value, 16))[2:]) <= 8:
                        bit_ls.append(format(int(value, 16), '08b'))
                    elif len(bin(int(value, 16))[2:]) <= 16:
                        bit_ls.append(format(int(value, 16), '16b'))
                    elif len(bin(int(value, 16))[2:]) <= 32:
                        bit_ls.append(format(int(value, 16), '32b'))
                    else:
                        bit_ls.append(format(int(value, 16), '064b'))
                    
                    
                
            
            
            
            df = pd.DataFrame(data)
            df["Value(Dec)"] = dec_ls
            df["Value(Bin)"] = bit_ls
            df["Datetime"] = time_ls
            
           # df["Value(Bin)"] = bit_ls
            df = df.replace('', np.nan)
            df = df.fillna("")
            
            styles = [dict(selector="th", props=[("color", "black"),
            ("border", "px solid #eee"),
            ("padding", "10px 8px"),
            ("border-collapse", "collapse"),
            ("background", "#A1C9D7"),
            ("text-transform", "uppercase"),
            ("font-size", "15px")
            ]),
            # styling methods for title of dataset
              dict(selector="caption",
              props=[("caption-side","top"),
                     ("text-align", "center"),
                     ("font-size", "30"),
                     ("color", 'black'),
                     ("font-family",'italic'),
                     ("background-color", "beige")])]
            
            
            df_styled = df.style.set_properties(**{'color':'black','font-size':'14'})\
            .set_table_styles(styles)\
            .set_caption(f"Register Values Lifecycle\n{self.filename_csv}")\
            .applymap(lambda aling_text: 'text-align: center')\
            .applymap(lambda assign_size: 'font-size: 20px')\
            .apply(highlight_col, axis = 1)

        # Convert to HTML
            #df_html = df_styled.render()
            print("CREATED DF HTML FILE!!!")
            df_html = df_styled.to_html()

            # Write to file
            with open(f"{self.filename_html}", "w") as file:
                file.write(df_html)
        
            # Export the DataFrame to a CSV file
            df.to_csv(self.filename_csv, index=False)
            self.html_file.emit(str(self.filename_html))
            print("Emitted signal", self.filename_html)
             

            
        except Exception as e:
            
            self.error.emit(str(e))
            self.stop()
            

    def stop(self):
        
        """
        Stop the reading process.

        Emits the finished signal.
        """
        self.READ_STATUS = False
        if not self.READ_ERROR and self.records_file:
            self.store_records_to_file()
        self.finished.emit()

class LTSSM_Worker(QObject):
    finished = pyqtSignal()
    core_reset = pyqtSignal()
    error = pyqtSignal(str)
    ltssm_img = pyqtSignal(object)
    
    
    def __init__(self, versal):
        """
        Initialize the LTSSM Worker.

        Args:
            device (object): The device instance to display the LTSSM Plot from.           
        """
        super().__init__()
        self.versal = versal
        self.refresh_status = True
        
    def scan_ltssm_graph(self):
        
        """
        Display the LTSSM graph and continuously refresh it in real-time.

        This method displays the LTSSM Graph in real-time. If no PCIe core is found, it emits an error signal
        and finishes the process. Otherwise, it continuously refreshes the LTSSM graph by calling the
        `refresh` method of the PCIe core and updates the LTSSM image displayed in the GUI using the
        `ltssm_img` signal.

        Raises:
            Exception: If an error occurs during the scan or refreshing process, it is caught, and
                       an error signal is emitted. The PCIe scan is then stopped.
        """
        
        try:
            
            if self.versal.pcie_core is None:
                self.error.emit("No PCIe Core found in this design!")
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
            self.stop()
            return
        
        try:

            while self.refresh_status:
                self.versal.pcie_core.refresh()
                ltssm_plt = self.versal.pcie_core.get_plt()

                ltssm_plt.title("LTSSM")

                # Save the plot image to a buffer
                buffer = io.BytesIO()
                ltssm_plt.savefig(buffer, format='png')
                buffer.seek(0)

                # Convert the image buffer to QImage
                ltssm_image = QImage.fromData(buffer.getvalue())

                # Emit the ltssm_img signal with the QImage
                self.ltssm_img.emit(ltssm_image)

                ltssm_plt.close()
                time.sleep(0.01)
                
                
        except Exception as e:
            self.refresh_status = False
            self.error.emit(str(e))
            self.stop()
        
    
        
    def stop(self):
        """
        Stop the PCIe scan.

        This method sets the `refresh_status` flag to False, indicating that the scan should stop.
        It emits the `finished` signal to indicate that the process is complete.
        """
        self.refresh_status = False
        self.finished.emit()
        
class IbertWorker(QObject):
    finished = pyqtSignal()
    ibert_information = pyqtSignal(list)
    
    widget_link_properties = pyqtSignal(list)
    link_set = pyqtSignal()
    eye_progress = pyqtSignal(list)
    eye_scan_status = pyqtSignal(int, str)
    eye_scan_done = pyqtSignal(str)
    eye_scan_picture = pyqtSignal(list)
    
    def __init__(self, versal, main_window):
        super().__init__()
        
        self.versal = versal
        self.main_window = main_window
        self.eye_scans_length = len(self.versal.ibert_links)
        
        
    
    def start_eye_scans(self):
        horizontal_step = int(self.main_window.horizontalStepComboBox.currentText())
        vertical_step = int(self.main_window.verticalStepComboBox.currentText())
        horizontal_range = str(self.main_window.horizontalRangeComboBox.currentText())
        vertical_range = str(self.main_window.verticalRangeComboBox.currentText())
        target_ber = float(self.main_window.targetBERComboBox.currentText())

        for i, eye_scan in enumerate(self.versal.eye_scans):
            eye_scan.progress_callback = self.scan_eye_progress(i, eye_scan)
            eye_scan.done_callback = self.scan_done_event_handler
            eye_scan.params[EYE_SCAN_HORZ_STEP].value = horizontal_step
            eye_scan.params[EYE_SCAN_VERT_STEP].value = vertical_step
            eye_scan.params[EYE_SCAN_HORZ_RANGE].value = horizontal_range
            eye_scan.params[EYE_SCAN_VERT_RANGE].value = vertical_range
            eye_scan.params[EYE_SCAN_TARGET_BER].value = target_ber
            eye_scan.start(show_progress_bar=False)
            eye_scan.wait_till_done()
            
            
    

    
    def plot_eye_scans(self):
        try:
            for i, scan in enumerate(self.versal.eye_scans):
                self.eye_scan_status.emit(i, scan.status)
                self.eye_scan_picture.emit([i,scan])
                
        except Exception as e:
            print(e)

            
    def scan_eye_progress(self, index, eye_scan_obj):      
        def scan_progress_event_handler(progress_percent: float):
            self.eye_progress.emit([int(index), round(progress_percent)])
            self.eye_scan_status.emit(index, eye_scan_obj.status)
        return scan_progress_event_handler
        
    
    def scan_done_event_handler(self, eye_scan_obj):
        self.eye_scans_length -= 1
        if self.eye_scans_length == 0:
            self.plot_eye_scans()
            self.stop()
            
            
    def stop(self):
        self.finished.emit()
        
        

    
        

class ILA_Worker(QObject):
    dataframe_signal = pyqtSignal(pd.DataFrame)
    finished = pyqtSignal()
    ila_core_status = pyqtSignal(str)
    ila_is_armed_status = pyqtSignal(int)
    csv_file_size_signal = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, versal, capture_mode_bool, trigger_mode, window_count, data_depth, trigger_position, csv_file):
        super().__init__()
        
        self.versal = versal
        self.selected_ila = versal.selected_ila
        self.single_capture_mode = capture_mode_bool
        self.trigger_mode = trigger_mode
        self.window_count = window_count
        self.data_depth = data_depth
        self.trigger_position = trigger_position
        self.monitor_status = False
        self.table_range = 0
        self.breakByButton = False
        
        self.csv_file = csv_file
    
        
    @pyqtSlot()
    def run_immediate_trigger(self):
        
        try:
            while True:
                
                if self.breakByButton:
                    break
                    
                self.selected_ila.run_trigger_immediately(trigger_position = self.trigger_position,
                                                          window_count = self.window_count,
                                                          window_size = self.data_depth
                                                         )
                self.selected_ila.upload()
                samples = self.selected_ila.waveform.get_data()
                df = pd.DataFrame(samples)
                self.dataframe_signal.emit(df)
                self.store_ila_data_to_csv(self.csv_file, samples)
                size = self.get_file_size_in_mb(self.csv_file)
                self.csv_file_size_signal.emit(f"{size:.3f} MegaBytes")
                
    
                if self.single_capture_mode:
                    break
                    
                
                    
            self.stop()
                
        except Exception as ex:
            self.error.emit(str(ex))
            self.stop()
            
        
    def store_ila_data_to_csv(self, csv_file:str, waveform_sample_data: object):
        
        if csv_file is None or waveform_sample_data is None:
            return
        
        if not os.path.exists(csv_file):
            # Create a new file and write the header
            with open(csv_file, "w", newline="") as csvfile:
                csv_writer = csv.writer(csvfile)
                # Write the header row
                csv_writer.writerow(list(waveform_sample_data.keys()))

        with open(csv_file, "a", newline = "") as csvfile:
            csv_writer = csv.writer(csvfile)

            for sample_idx in range(len(next(iter(waveform_sample_data.values())))):
                row = [waveform_sample_data[probe_name][sample_idx] for probe_name in waveform_sample_data.keys()]
                csv_writer.writerow(row)
                
        
            
            
    def get_file_size_in_mb(self, file:str):
        if file is None:
            return None
        
        file_stats = os.stat(file)
        mb_file_size = file_stats.st_size / (1024 * 1024)
        return mb_file_size
    
    @pyqtSlot() 
    def run_basic_trigger(self):
        
        def status_progress(future):
            
            st = future.progress
            buffer_fill_size = 0
            print("progress: ", st)
            if st:
                self.ila_core_status.emit(str(st.capture_state))
                try:
                    buffer_fill_size = int(100 / (st.samples_requested / st.samples_captured))
                except ZeroDivisionError:
                    buffer_fill_size = int(st.samples_requested)
                self.ila_is_armed_status.emit(buffer_fill_size)
                
                    
                
                
            
        def status_done(future):
            
            st = future.result
            if st:
                self.ila_core_status.emit(str(st.capture_state))
            if future.error:
                self.ila_core_status.emit(str(future.error))
           
            

        self.ila_is_armed_status.emit(0)
        try:
            while True:
               
                if self.breakByButton:
                    break
                
                self.selected_ila.run_basic_trigger(trigger_position=self.trigger_position,
                                                    window_count=self.window_count,
                                                    window_size=self.data_depth)
                
                
                
                self.monitor_status = self.selected_ila.monitor_status(max_wait_minutes = 0.01, progress = status_progress, done = status_done)    
                
                
                if self.monitor_status.result:
                    self.selected_ila.upload()
                    samples = self.selected_ila.waveform.get_data()
                    df = pd.DataFrame(samples)
                    self.dataframe_signal.emit(df)
                    self.ila_is_armed_status.emit(100)
                    self.store_ila_data_to_csv(self.csv_file, samples)
                    size = self.get_file_size_in_mb(self.csv_file)
                    self.csv_file_size_signal.emit(f"{size:.3f} MegaBytes")
                else:
                    continue
                
                if self.single_capture_mode:
                    break
            self.stop()
        except Exception as ex:
            print("Erorr is inside while loop!")
            self.error.emit(str(ex))
            self.stop()
        
   
    def stop(self):
        #self.single_capture_mode = False
        self.finished.emit()
   

        


                
                
  
        
                
    
        
        
        
        
        
        
        
        


# In[ ]:




