# Copyright (C) 2024, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT


import os
from chipscopy import create_session, delete_session
from chipscopy.api.ibert import delete_eye_scans, delete_links


class VersalSession:
    """
    VersalSession - A class for managing connections and operations with a Versal device.

    The VersalSession class provides methods to connect to a Versal device, discover and set its cores,
    and perform operations such as deleting the current session.
    
    Main Purpose of this class is to encapsulate all core device data into one unit.

    Attributes:
        hw_server_url (str): The URL of the hardware (HW) server.
        cs_server_url (str): The URL of the control and status (CS) server.
        session (object): The ChipScoPy session object.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/session.html
                                
        device (object): The connected Versal device object.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/device.html
                                
        ibert_core (object): The IBERT (Integrated Bit Error Ratio Test) core of the device.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/ibert.html
                                
        ibert_links (object): The links associated with the IBERT core.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/ibert/link.html
                                
        eye_scans (object): The eye scans performed on the device.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/ibert/eye_scan.html
                                
        pcie_core (object): The PCIe (Peripheral Component Interconnect Express) core of the device.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/pcie/references/pcie.html
                                
        ila_cores (object): The ILA (Integrated Logic Analyzer) cores of the device.
                                Reference -> https://xilinx.github.io/chipscopy/2023.1/ila.html

    Methods:
        __init__(hw_server_url, cs_server_url):
            Initialize the VersalSession object with the provided HW and CS server URLs.

        initialize_attributes():
            Initialize all the class attributes.

        connect():
            Connect to the Versal device.

        discover_cores(probes_file):
            Discover and set the IBERT, PCIe, and ILA cores of the device.

        delete_current_session():
            Delete the current session, including links, eye scans, and the ChipScoPy session itself.
    """
    def __init__(self, main_window):
        """
        Initialize the Device.

        
        
        Args:
            hw_server_url (str): The URL of the hardware (HW) server.
            cs_server_url (str): The URL of the control and status (CS) server.
        """
        self.initialize_attributes()
       
        self.main_window = main_window
        
    def initialize_attributes(self):
        self.session = None
        self.device = None
        self.memory_targets = None
        self.ibert_core = None
        self.ibert_links = None
    
        self.eye_scans = None
        self.pcie_core = None
        self.ila_cores = None
        self.selected_ila = None
        self.ILA_selected_signals = []
        
        self.pdi_file = None
        self.ltx_file = None
        
    def connect(self):
        """
        Connect to the device.

        Establishes a session with the (HW) and (CS) servers.

        Returns:
            self.device (object): The device object that is connected
        """
      
        self.HW_SERVER = os.getenv("HW_SERVER_URL", self.main_window.hwServer_Line.text().replace(" ", ""))
        self.CS_SERVER = os.getenv("CS_SERVER_URL", self.main_window.csServer_Line.text().replace(" ", ""))
        self.refresh_session()
        
        
        

    def refresh_session(self):
    
        self.session = create_session(cs_server_url=self.CS_SERVER, hw_server_url=self.HW_SERVER, bypass_version_check=True)
        print("Session: ", self.session)
        
        self.refresh_device()
        
        
        
    def refresh_device(self):
        if self.is_session_available:
            self.device = self.session.devices.get(family = "versal")
            self.memory_targets = self.device.memory_target_names
            print("Device: ", self.device)
            print("Memory Targets: ", self.memory_targets)
            
    
    
    @property
    def is_device_available(self):
        return self.device is not None
    @property
    def is_session_available(self):
        return self.session is not None
    
    
   
    
    def discover_cores(self):
        """
        Discover and set the IBERT, PCIe, and ILA cores of the device.

        Args:
            probes_file (str): The path to the probes file.

        Returns:
            None
        """
        
        if self.device is None:
            self.ibert_core = None
            self.pcie_core = None
            self.ila_cores = None
            return

        self.device.discover_and_setup_cores(ibert_scan=True)

        try:
            self.ibert_core = self.device.ibert_cores.at(index=0)
           # self.ibert_core.reset()
        except IndexError:
            self.ibert_core = None
        
        
        if self.ltx_file is not None:
            self.device.discover_and_setup_cores(ltx_file=self.ltx_file)
            try:
                self.pcie_core = self.device.pcie_cores[0]
            except IndexError:
                self.pcie_core = None

            try:
                self.ila_cores = self.device.ila_cores
                if len(self.ila_cores) == 0:
                    self.ila_cores = None
            except Exception:
                self.ila_cores = None
        
        
    
    def delete_current_session(self):
        """
        Delete the current session, including links, eye scans, and the ChipScoPy session itself.
        """
        try:
            delete_links(self.ibert_links)
        except:
            pass
        try:
            delete_eye_scans(self.eye_scans)
        except:
            pass
        try:
            delete_session(self.session)
        except:
            pass
        self.initialize_attributes()
                
    



