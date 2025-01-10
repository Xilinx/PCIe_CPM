# Copyright (C) 2024, Advanced Micro Devices, Inc. All right reserved. 
# SPDX-License-Identifier: MIT

import pandas as pd
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush
from PyQt5.QtWidgets import QMainWindow, QPushButton, QFileDialog, QLabel, QVBoxLayout, QDialog, QApplication, \
    QMessageBox, QStyledItemDelegate
from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5 import uic

import os
import webbrowser
import sys
from typing import List
import re
import images


def show_error_message(message: str) -> None:
    """
    Show error message to the user when called.
    """
    QMessageBox.warning(None, "Error", message)


def clean_brackets_and_spaces(s: str):
    return s.replace("[","").replace("]","").replace(" ","")

def get_hex(s: str):
    return f"{hex(int(s,16))}"


def is_bit_field_valid(s: str):
    if is_value_nan(s):
        return False

    # Regular expression pattern for valid bit fields
    #pattern = r'\(\d+(:\d+)?\)'
    pattern = r"(\d+)|(\[\d+\])|(\[\d+:\d+\])|(\d+:\d+)"

    # Check if the bit_field matches the pattern
    return bool(re.match(pattern, s))

def is_address_valid(s: str):
    if is_value_nan(s):
        return False

    if "-" in s:
        return False

    return True

def is_value_nan(s: str):
    # if the value is NaN, the comparison s != s evaluates to True
    if s != s:
        return True

    return False

def calculate_width(bit_field: str):


    try:
        width = bit_field.split(":")
        result = int(width[0]) - int(width[1]) + 1
    except IndexError:
        result = 1

    return result

def hex_to_binary(hex_val: str, binary_length: int = 32):
    return f"{int(hex_val, 16):0{binary_length}b}"

def binary_to_hex(bin_val: str):
    if bin_val and not is_value_nan(bin_val):
        return hex(int(str(bin_val), 2))
    else:
        return ''

def binary_to_dec(bin_val: str):
    if bin_val and not is_value_nan(bin_val):
        return str(int(str(bin_val), 2))
    else:
        return ''


def is_hex(s: str):
    try:
        int(s, 16)
        return True
    except (ValueError, TypeError):
        return False

def is_string_empty(s: str):
    if len(s) == 0:
        return True
    else:
        return False

def load_dataframe_from_csv(file: str, encod = 'utf-8'):
    return pd.read_csv(file, encoding = encod)

def load_dataframe_from_txt(file: str, encod = 'utf-8'):
    return pd.read_fwf(file, encoding = encod)

def drop_rows_with_missing_values(df: pd.DataFrame, columns_to_check: list):
    if df is not None:
        df.dropna(subset=columns_to_check, how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)


def add_column_of_data_to_df(df: pd.DataFrame, column_name: str, data_ls: list):
    if df is not None:
        df[column_name] = data_ls


def export_df(df: pd.DataFrame, filename: str):
    formats = {
        "csv": df.to_csv,
        "html": df.to_html
    }

    file_extension = filename.split(".")[-1]
    if file_extension in formats:
        export_function = formats[file_extension]
        export_function(filename)
        return filename
    else:
        show_error_message("Unsupported format!")
        return None


def output_to_html(output_filename, merged_df, address):
    """
    Output the register definition DataFrame to an HTML file with highlighting.

    Args:
        output_filename (str): Name of the output HTML file.
    """

    def highlight_col(row):
        """
        Custom styling function to highlight rows based on address presence.

        Args:
            row (Series): Row of the DataFrame.

        Returns:
            list: List of CSS background-color values for each cell in the row.
        """
        colors = ['#C0C0C0', '#EAD2A8']  # Add more colors as needed
        if row[address] != "":
            return ["background-color:" + colors[0] for i in range(len(row))]
        return ["background-color:" + colors[1] for i in range(len(row))]

    styles = [dict(selector="th", props=[("color", "black"),
                                         ("border", "1px solid #eee"),
                                         ("padding", "10px 4px"),
                                         ("border-collapse", "collapse"),
                                         ("background", "#A1C9D7"),
                                         ("text-transform", "uppercase"),
                                         ("font-size", "12px")
                                         ]),
              # styling methods for title of dataset
              dict(selector="caption",
                   props=[("caption-side", "top"),
                          ("text-align", "center"),
                          ("font-size", "30"),
                          ("color", 'black'),
                          ("font-family", 'italic'),
                          ("background-color", "beige")])]


    register_def_styled = merged_df.style.set_properties(**{'color': 'black', 'font-size': '14'}) \
        .set_table_styles(styles) \
        .set_caption(output_filename) \
        .apply(highlight_col, axis=1)

    register_def_html = register_def_styled.to_html()

    # Write to file
    with open(output_filename, "w") as file:
        file.write(register_def_html)

    return output_filename

class RegisterDefinition:
    def __init__(self, filename: str, address_column: str = 'address', width_column: str = 'width', encoding: str = 'utf-8'):
        self._filename = filename
        self._address_column = address_column
        self._width_column = width_column

        self._df = load_dataframe_from_csv(filename, encoding)

        self._process_dataframe()

        for i, addr in enumerate(self._df[address_column]):
            if is_hex(addr):
                self._df.loc[i, address_column] = get_hex(addr)


    @property
    def df(self):
        return self._df
    @property
    def address_column_name(self):
        return self._address_column

    @property
    def width_column_name(self):
        return self._width_column

    def _process_dataframe(self):
        if self._df is not None:
            # Select all columns except the first one which is the register column
            columns_to_check = list(self._df.columns)[1:]
            drop_rows_with_missing_values(self._df, columns_to_check)
            self._df.fillna('', inplace=True)



class RegisterValues:
    def __init__(self, filename: str, offset_column: str, value_column: str, encoding: str = 'utf-8'):
        self._df = load_dataframe_from_txt(filename, encoding)

        self._offset_column = offset_column
        self._value_column = value_column

        self._binary_column = None
        self._df[offset_column] = [clean_brackets_and_spaces(addr) for addr in self._df[offset_column]]
        self._df[offset_column] = [get_hex(addr) for addr in self._df[offset_column]]

        # split columns where they are attached as sometimes
        # generated text files have this issue
        for column in self._df.columns:
            if column.__contains__(' '):
                self._df[column.split(' ')] = self._df[column].str.split(' ', n = 1, expand=True)
                self._df.drop(columns=[column], inplace=True)


    @property
    def offset_column_name(self):
        return self._offset_column

    @property
    def value_column_name(self):
        return self._value_column

    @property
    def binary_column_name(self):
        return self._binary_column

    @property
    def df(self):
        return self._df

    def add_binary_values_column(self, new_column_name):
        if self._df is not None:
            bit_ls = [hex_to_binary(hex_val) for hex_val in self._df[self._value_column]]
            self._df[new_column_name] = bit_ls
            self._binary_column = new_column_name


class RegisterParser:
    def __init__(self):
        self._register_definitions = None
        self._register_values = None
        self._merged_df = None
        self._register_data_array = []

    def set_definitions_file(self, filename: str,
                             address_column: str = "address",
                             width_column: str = "width",
                             encoding: str = "utf-8"):

        self._register_definitions = RegisterDefinition(filename, address_column, width_column, encoding)

    def set_values_file(self, filename: str,
                        offset_column: str = "Offset",
                        value_column: str = "Value(Hex)",
                        encoding: str = "utf-8"):
        self._register_values = RegisterValues(filename, offset_column, value_column, encoding)


    def get_definitions_df(self):
        if self._register_definitions is not None:
            return self._register_definitions.df

    def get_values_df(self):
        if self._register_values is not None:
            return self._register_values.df


    def parse_register_definition_and_value_files(self, bin_column):

        reg_def = self.get_definitions_df()

        if reg_def is None:
            show_error_message("No Register Definition File was detected!")
            return

        reg_val = self.get_values_df()

        if reg_val is None:
            show_error_message("No Register Definition File was detected!")
            return


        address_column = self._register_definitions.address_column_name
        width_column = self._register_definitions.width_column_name
        offset_column = self._register_values.offset_column_name

        self._register_values.add_binary_values_column(bin_column)

        bit_ls = self.parse_binary_values(reg_def, reg_val, address_column, width_column, offset_column, bin_column)
        self._merged_df = self.create_merged_dataframe(reg_def, bit_ls, bin_column)

    def parse_binary_values(self, reg_def, reg_val, address_column, width_column, offset_column, bin_column):
        bit_ls = []
        init = 0
        bit_value = 0
        for n, address in enumerate(reg_def[address_column].to_list()):

            if address in reg_val[offset_column].to_list():
                bit_value = reg_val.loc[reg_val[offset_column] == address, bin_column].iloc[0]
                init = 0
                bit_ls.append(bit_value)
            else:
                try:
                    bit_field = reg_def[width_column][n]
                    if is_bit_field_valid(bit_field):
                        width = clean_brackets_and_spaces(bit_field)
                        width_size = calculate_width(width)
                        bit_ls.append(bit_value[init: init + width_size])
                        init = init + width_size
                    else:
                        bit_ls.append('')
                except TypeError as e:
                    bit_ls.append('')
        return bit_ls

    def create_merged_dataframe(self, reg_def, bit_ls, bin_column):
        merged_df = self.get_definitions_df().copy()
        add_column_of_data_to_df(merged_df, bin_column, bit_ls)
        add_column_of_data_to_df(merged_df, "Value(Hex)", [binary_to_hex(b) for b in bit_ls])
        add_column_of_data_to_df(merged_df, "Value(Dec)", [binary_to_dec(b) for b in bit_ls])
        return merged_df


    def get_merged_df(self):
        if self._merged_df is not None:
            return self._merged_df

    def get_merged_df_columns(self):
        if self._merged_df is not None:
            return list(self._merged_df.columns)

    def get_register_data_array(self):

        if self._merged_df is None:
            show_error_message("No parsed dataframe detected!")
            return

        columns = self.get_merged_df_columns()
        address_column = self._register_definitions.address_column_name


        register = 0
        for n, address in enumerate(self._merged_df[address_column].to_list()):
            if not is_string_empty(address):
                register = RegisterData()
                register.initialize_headers(columns)

                for col in columns:
                    register.insert_data(col, self._merged_df[col][n])

                self._register_data_array.append(register)
            else:
                if register:
                    for col in columns:
                        register.insert_data(col, self._merged_df[col][n])


        return self._register_data_array


    def clear_register_data_array(self):
        for register in self._register_data_array:
            register.clear()


class RegisterData:
    def __init__(self):
        self.data = {}

    def insert_data(self, header: str, data: []):
        self.data[header].extend(data)

    def insert_data(self, header: str, data: str):
        self.data[header].append(data)

    def initialize_headers(self, columns: List[str]):
        for column in columns:
            self.data[column] = []

    @property
    def headers(self):
        return list(self.data.keys())

    @property
    def df(self):
        return pd.DataFrame(self.data)


    def get_register_name(self):
        return self.data["register"][0]

    def get_register_values(self):
        return list(self.data.values())


    def clear(self):
        self.data.clear()



def browse_file(window):
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly
    file_name, _ = QFileDialog.getOpenFileName(window,
                                               "QFileDialog.getOpenFileName()", "",
                                               "All Files (*);;Python Files (*.py)",
                                               options=options)
    return file_name


class InstructionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instructions")

        layout = QVBoxLayout()

        instructions = """
        1) The Register Parser Tool requires two input files to work:
        \t-> Register Definition File
        \t-> Register Values File
        2) Browse and select the Register Definition File:
        \t-> Enter Column Header with Register Addresses
        \t-> Enter Column Header with Register Widths
        3) Browse and select the Register Values File:
        \t-> Enter Column Header with Register Values
        \t-> Enter Column Header with Register Offsets
        4) Enter the name for the new generated output File
        5) Parse and generate new file
        6) Display the prepared dataset in HTML Format
        """

        label = QLabel(instructions)
        label.setWordWrap(True)

        layout.addWidget(label)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self.setLayout(layout)


class RegisterParserGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("ui_designs/register_parser_gui.ui", self)
        self.initial_menu_frame_width = 0
        self.initial_menu_frame_height = 0
        QTimer.singleShot(0, self.get_initial_size)

    def clear_layout(self):
        if self.search_registers_vertical_layout is not None:
            while self.search_registers_vertical_layout.count():
                item = self.search_registers_vertical_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def get_initial_size(self):
        self.initial_menu_frame_width = self.search_registers_available_frame.width()
        self.initial_menu_frame_height = self.search_registers_available_frame.height()

    def toggle_menu(self):
        width = self.search_registers_available_frame.width()
        if width > 0:
            self.search_registers_available_frame.setFixedSize(0, 0)
        else:
            self.search_registers_available_frame.setFixedSize(
                self.initial_menu_frame_width,
                self.initial_menu_frame_height)

    def show_instructions(self):
        dialog = InstructionsDialog(self)
        dialog.exec()


class RegisterParserController:
    def __init__(self, view, model):
        self.view = view
        self.model = model
        self.registerTableModel = RegisterTableModel()
        self.view.register_tableview.setModel(self.registerTableModel)

        self.view.open_file_parser_button.clicked.connect(self.open_file_parser_gui)
        self.view.menu_button.clicked.connect(self.view.toggle_menu)
        self.view.output_to_csv_button.clicked.connect(self.open_output_file_in_csv)
        self.view.output_to_html_button.clicked.connect(self.open_output_file_in_html)
        self.view.search_registers_button.clicked.connect(self.display_searched_registers)
        self.view.clearButton.clicked.connect(self.clear_displayed_registers)

    def display_gui(self):
        self.view.show()

    def open_file_parser_gui(self):
        self.fileParserWindow = FileParserGUI()
        self.fileParserController = FileParserController(self.model, self.fileParserWindow)
        self.fileParserWindow.merged_df_ready.connect(self.handle_merged_df)
        self.fileParserWindow.show()

    def handle_merged_df(self):

        try:
            self.view.clear_layout()
            self.view.loaded_file_label.setText(f"File: {self.model.output_csv_file}")
            registers = self.model.register_dicts
            self.view.registers_found_label.setText(f"Total registers found: {len(registers)}")
            self.create_register_buttons(registers)

        except Exception as e:
            show_error_message(e)

    def display_searched_registers(self):
        self.view.clear_layout()
        if self.model.register_dicts:
            registers = self.model.register_dicts

            key = self.view.search_register_line_edit.text()

            registers_to_display = []
            for register in registers:
                if key in register.get_register_name():
                    registers_to_display.append(register)

            self.create_register_buttons(registers_to_display)
            self.view.registers_found_label.setText(f"Total registers found: {len(registers_to_display)}")

    def create_register_buttons(self, registers):
        for i, register in enumerate(registers):
            button = RegisterButton(register,
                                    self.registerTableModel,
                                    self.view.register_tableview,
                                    self.view.loaded_register_label)

            self.view.search_registers_vertical_layout.addWidget(button)

    def clear_displayed_registers(self):
        if self.model.register_dicts:
            registers = self.model.register_dicts
            self.view.clear_layout()
            self.create_register_buttons(registers)
            self.view.registers_found_label.setText(f"Total registers found: {len(registers)}")

    def open_output_file_in_csv(self):
        if self.model.output_csv_file:
            os.startfile(self.model.output_csv_file)

    def open_output_file_in_html(self):
        if self.model.output_html_file:
            webbrowser.open(self.model.output_html_file)


class RegisterButton(QPushButton):
    def __init__(self, register, model, view, label):
        super().__init__(register.get_register_name())
        self._register = register
        self._model = model
        self._view = view
        self._label = label
        self.clicked.connect(self.display_register_data)

    def display_register_data(self):
        try:
            self._label.setText(f"Register: {self._register.get_register_name()}")
            self._model.set_register_data(self._register)
            self._model.update_data()
            self._view.resizeRowsToContents()
            self._view.resizeColumnsToContents()
        except Exception as e:
            show_error_message(e)


class RegisterTableModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._register = None

    def set_register_data(self, register):
        self._register = register

    def update_data(self):
        if self._register is None:
            print("No register data has been assigned to this model!\n")
            return

        self.clear()
        self.setHorizontalHeaderLabels(self._register.headers)
        for row_idx, row in enumerate(self._register.get_register_values()):
            for col_idx, value in enumerate(row):
                item = QStandardItem(str(value))
                self.setItem(col_idx, row_idx, item)


class FileParserGUI(QMainWindow):
    merged_df_ready = pyqtSignal()

    def __init__(self):
        super().__init__()
        uic.loadUi("ui_designs/file_parser_gui.ui", self)
        self.openManual_QAction.triggered.connect(self.show_instructions)

    def update_register_definition_filename_line(self, filename: str) -> None:
        self.definition_filename_lineEdit.setText(filename)

    def update_register_values_filename_line(self, filename: str) -> None:
        self.values_filename_lineEdit.setText(filename)

    def get_definition_address_header(self):
        address_header = self.definition_header_lineEdit.text()
        return address_header
        # add error checking if lineEdit is empty

    def get_definition_width_header(self):
        width_header = self.definition_width_lineEdit.text()
        return width_header

    def get_definition_file_encoding(self):
        return self.definition_encoding_lineEdit.text() or "utf-8"

    def get_values_offset_header(self):
        offset_header = self.values_offset_lineEdit.text()
        return offset_header

    def get_values_header(self):
        values_header = self.values_header_lineEdit.text()
        return values_header

    def get_values_file_encoding(self):
        encoding = self.values_encoding_lineEdit.text() or "utf-8"

    def set_html_output_file_line(self, html_output_file):
        self.html_output_file_lineEdit.setText(html_output_file)

    def set_csv_output_file_line(self, csv_output_file):
        self.csv_file_output_lineEdit.setText(csv_output_file)

    def show_instructions(self):
        dialog = InstructionsDialog(self)
        dialog.exec()


class ParserModel:
    def __init__(self):
        self.definitions_file = None
        self.values_file = None
        self.output_html_file = None
        self.output_csv_file = None
        self.merged_df = None
        self.register_dicts = None

    def set_definitions_file(self, file: str) -> None:
        self.definitions_file = file

    def set_values_file(self, file: str) -> None:
        self.values_file = file


class FileParserController:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self.connect_buttons()

    def connect_buttons(self):
        self.view.browse_definition_file_button.clicked.connect(self.retrieve_register_definition_file)
        self.view.browse_values_file_button.clicked.connect(self.retrieve_register_values_file)
        self.view.parse_input_files_button.clicked.connect(self.generate_output_file)
        self.view.analyze_parsed_data_button.clicked.connect(self.open_merged_df_for_analysis)

    def display_ui(self):
        self.view.show()

    def retrieve_register_definition_file(self):
        file = browse_file(self.view)
        if file:
            self.model.set_definitions_file(file)
            self.view.update_register_definition_filename_line(file)

    def retrieve_register_values_file(self):
        file = browse_file(self.view)
        if file:
            self.model.set_values_file(file)
            self.view.update_register_values_filename_line(file)

    def generate_output_file(self):

        definition_address_header = self.view.get_definition_address_header()
        definition_width_header = self.view.get_definition_width_header()
        definition_file_encoding = self.view.get_definition_file_encoding()

        values_offset_header = self.view.get_values_offset_header()
        values_header = self.view.get_values_header()
        values_file_encoding = self.view.get_values_file_encoding()

        parser = RegisterParser()

        try:
            parser.set_definitions_file(self.model.definitions_file,
                                        address_column=definition_address_header,
                                        width_column=definition_width_header,
                                        encoding=definition_file_encoding)


            parser.set_values_file(self.model.values_file,
                                   offset_column=values_offset_header,
                                   value_column=values_header,
                                   encoding=values_file_encoding)

            parser.parse_register_definition_and_value_files(bin_column="Value(Bin)")

            merged_df = parser.get_merged_df()

            if merged_df is not None:
                base_name = os.path.splitext(os.path.basename(self.model.definitions_file))[0]
                output_html_file = f"{base_name}_merged_data.html"
                output_csv_file = f"{base_name}_merged_data.csv"

                #exported_html_file = export_df(merged_df, output_html_file)
                exported_html_file = output_to_html(output_html_file, merged_df, definition_address_header)
                exported_csv_file = export_df(merged_df, output_csv_file)

                self.model.output_html_file = exported_html_file
                self.model.output_csv_file = exported_csv_file
                self.model.merged_df = merged_df
                self.model.register_dicts = parser.get_register_data_array()

                self.view.set_html_output_file_line(exported_html_file)
                self.view.set_csv_output_file_line(exported_csv_file)


        except Exception as e:

            show_error_message(str(e))
            return

    def open_merged_df_for_analysis(self):
        self.view.merged_df_ready.emit()










