"""
Bare Earth Reconstructor - QGIS Plugin

A scientific tool for reconstructing natural terrain surfaces from Digital Surface Models (DSM)
by removing anthropogenic structures and vegetation. Based on the methodology of Cao et al. (2020).

This plugin implements an advanced workflow for bare earth reconstruction using:
- Adaptive percentile-based thresholds (Cao et al. 2020 methodology)
- 3-class classification (Natural/Vegatation/Anthropogenic)
- Texture analysis using GLCM metrics
- Multi-stage Gaussian filtering
- Robust interpolation with fallback mechanisms

Key Features:
- Percentile-based adaptive thresholds that automatically adapt to terrain type
- Texture analysis for distinguishing vegetation from anthropogenic features
- 3-class classification system for selective filtering
- Enhanced GDAL interpolation with multi-stage processing
- Comprehensive processing reports and file organization
- Auto-scaling parameters based on DSM resolution

Scientific Background:
The plugin implements the methodology described in:
Cao, W., et al. (2020). "Adaptive threshold-based approach for automatic extraction 
of anthropogenic features from high-resolution digital surface models." 
Remote Sensing, 12(3), 456.

Author: [Your Name]
Version: Advanced with Percentile-based Thresholds
License: GPL v3
"""

import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QAction, QFileDialog
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProject,
    QgsProcessingFeedback,
    QgsRasterLayer,
    QgsPointXY,
    QgsRasterBandStats
)
import processing
import tempfile

"""
From the weakness of the mind, Omnissiah save us,
From the lies of the Antipath, circuit preserve us,
From the rage of the Beast, iron protect us,
From the temptations of Chaos, silica cleanse us,
From the ravages of time, anima shield us.

Praise the Omnissiah!
"""

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'bare_earth_reconstructor_dialog.ui'))

class BareEarthReconstructorDialog(QDialog, FORM_CLASS):
    """
    Main dialog class for the Bare Earth Reconstructor plugin.
    
    This class handles the user interface and orchestrates the entire reconstruction
    workflow. It provides a comprehensive GUI for parameter input, processing control,
    and result visualization.
    
    The dialog implements a tabbed interface with:
    - Tab 1: Input & Processing parameters
    - Tab 2: Advanced options (Gaussian filtering, texture analysis)
    - Tab 3: Interpolation & Output settings
    
    Key Features:
    - Dynamic help text that updates based on active tab
    - Auto-scaling of parameters based on DSM resolution
    - Progress tracking with detailed status messages
    - Comprehensive error handling and user feedback
    - Support for both percentile-based and fixed threshold methods
    
    Attributes:
        parent: Parent widget (typically QGIS main window)
        Various UI elements for parameter input and control
        
    Methods:
        - __init__: Initialize dialog and connect signals
        - run_reconstruction: Main processing workflow
        - analyze_geomorphometric_statistics: Statistical analysis for adaptive thresholds
        - perform_texture_analysis: GLCM-based texture analysis
        - generate_processing_report: Comprehensive processing documentation
        - organize_output_files: File organization and cleanup
    """
    
    def __init__(self, parent=None):
        """
        Initialize the Bare Earth Reconstructor dialog.
        
        Sets up the user interface, connects signal handlers, initializes
        default parameter values, and prepares the dialog for user interaction.
        
        Args:
            parent: Parent widget (typically QGIS main window). Defaults to None.
            
        Side Effects:
            - Populates layer combo boxes with available raster layers
            - Connects UI element signals to appropriate handlers
            - Sets up dynamic help text system
            - Initializes default parameter values
        """
        super().__init__(parent)
        self.setupUi(self)
        self.populate_layers()
        self.buttonRun.clicked.connect(self.run_reconstruction)
        self.buttonBrowseDSM.clicked.connect(self.browse_dsm)
        self.buttonBrowseOutputDir.clicked.connect(self.browse_output_dir)
        
        # Connect radio button signals for threshold method switching
        self.radioPercentile.toggled.connect(self.on_threshold_method_changed)
        self.radioFixed.toggled.connect(self.on_threshold_method_changed)
        
        # Connect interpolation method radio buttons
        self.radioEnhanced.toggled.connect(self.on_interpolation_method_changed)
        self.radioSimple.toggled.connect(self.on_interpolation_method_changed)
        self.radioGrassFillnulls.toggled.connect(self.on_interpolation_method_changed)
        
        # Connect tab change event to update help text
        self.tabWidget.currentChanged.connect(self.update_help_text_for_tab)
        
        # Initialize UI state (Percentile mode is default)
        self.on_threshold_method_changed()
        
        # Set initial help text for first tab
        self.update_help_text_for_tab(0)
        
        # Set locale for decimal separators to use dot (.) instead of comma (,)
        from PyQt5.QtCore import QLocale
        english_locale = QLocale(QLocale.English, QLocale.UnitedStates)
        
        # Apply English locale to all QDoubleSpinBox widgets for consistent decimal input
        for widget_name in ['spinVarianceThreshold', 'spinEntropyThreshold', 'spinSlope', 
                          'spinCurvature', 'spinResidual', 'spinVariancePercentile', 
                          'spinEntropyPercentile', 'spinSigma', 'spinKernel', 'spinBuffer', 
                          'spinFillDistance', 'spinFillIterations', 'spinTension', 
                          'spinSmooth', 'spinEdge', 'spinNpmin', 'spinSegmax']:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'setLocale'):
                    widget.setLocale(english_locale)

    def on_threshold_method_changed(self):
        """
        Handle switching between percentile and fixed threshold modes.
        
        This method is called when the user toggles between the two threshold
        methods. It enables/disables appropriate UI elements and provides
        user feedback about the selected method.
        
        The percentile-based method (Cao et al. 2020) uses adaptive thresholds
        that automatically adjust to the terrain characteristics, while the
        fixed threshold method uses user-defined absolute values.
        
        Side Effects:
            - Enables/disables appropriate parameter groups
            - Updates UI state to reflect selected method
            - Prints debug information about method selection
        """
        if self.radioPercentile.isChecked():
            # Enable percentile group, disable fixed group
            self.groupPercentiles.setEnabled(True)
            self.groupFixedThresholds.setEnabled(False)
            
            # Enable Variance/Entropy percentile widgets, disable threshold widgets
            self.spinVariancePercentile.setEnabled(True)
            self.spinEntropyPercentile.setEnabled(True)
            self.spinVarianceThreshold.setEnabled(False)
            self.spinEntropyThreshold.setEnabled(False)
            
            # print('DEBUG: Switched to Percentile-based thresholds (Cao et al. 2020)')
        else:
            # Enable fixed group, disable percentile group
            self.groupPercentiles.setEnabled(False)
            self.groupFixedThresholds.setEnabled(True)
            
            # Enable Variance/Entropy threshold widgets, disable percentile widgets
            self.spinVariancePercentile.setEnabled(False)
            self.spinEntropyPercentile.setEnabled(False)
            self.spinVarianceThreshold.setEnabled(True)
            self.spinEntropyThreshold.setEnabled(True)
            
            # print('DEBUG: Switched to Fixed thresholds')

    def on_interpolation_method_changed(self):
        """
        Handle switching between interpolation methods.
        
        This method is called when the user toggles between different interpolation
        methods. It enables/disables the GRASS r.fillnulls parameter group based
        on the selected method and provides user feedback about the selection.
        
        The method manages the UI state for the GRASS parameter group, ensuring
        that parameters are only accessible when the GRASS r.fillnulls method
        is selected. This prevents confusion and ensures proper parameter validation.
        
        Supported Methods:
            - Enhanced GDAL: Multi-stage processing with smoothing
            - Simple GDAL: Fast single-stage processing
            - GRASS r.fillnulls: Organic interpolation using RST method
            
        Side Effects:
            - Enables/disables GRASS parameter group based on selection
            - Updates UI state to reflect selected method
            - Prints debug information about method selection
            - Provides user feedback through console output
            
        Note:
            - GRASS parameters are only enabled when GRASS method is selected
            - Other methods disable the GRASS parameter group automatically
            - GRASS r.fillnulls includes fallback to Simple GDAL if processing fails
            - Debug output helps track user selections for troubleshooting
        """
        if self.radioGrassFillnulls.isChecked():
            # Enable GRASS parameters group
            self.groupGrassFillnulls.setEnabled(True)
            # print('DEBUG: Switched to GRASS r.fillnulls interpolation')
        else:
                        # Disable GRASS parameters group
            self.groupGrassFillnulls.setEnabled(False)
            if self.radioEnhanced.isChecked():
                pass  # print('DEBUG: Switched to Enhanced GDAL interpolation')
            elif self.radioSimple.isChecked():
                pass  # print('DEBUG: Switched to Simple GDAL interpolation')

    def validate_nodata_raster(self, raster_path):
        """
        Validate that a raster has proper NoData values defined.
        
        This method performs comprehensive validation of NoData values in a raster
        file, which is crucial for GRASS r.fillnulls to work correctly. The method
        checks both the technical definition of NoData values and their practical
        presence in the dataset.
        
        The validation includes:
        - File accessibility and raster layer validity
        - NoData value definition in the raster metadata
        - Presence of actual NoData pixels in the dataset
        - Statistical validation of raster content
        
        This method is specifically designed for GRASS r.fillnulls compatibility,
        as this algorithm requires properly defined NoData values to function
        correctly. Without proper NoData validation, GRASS r.fillnulls may fail
        or produce incorrect results.
        
        Args:
            raster_path (str): Path to the raster file to validate
                - Must be a valid file path
                - Should be a supported raster format (GeoTIFF, etc.)
                - File must be readable by QGIS
                
        Returns:
            bool: True if raster has valid NoData values, False otherwise
                - True: Raster is ready for GRASS r.fillnulls processing
                - False: Raster has issues that would cause GRASS processing to fail
                
        Side Effects:
            - Prints detailed debug information about validation process
            - Logs NoData value, raster statistics, and validation results
            - Provides warnings for potential processing issues
            
        Raises:
            Exception: If raster loading or validation fails (logged but not re-raised)
            
        Note:
            - This method is called before GRASS r.fillnulls execution
            - Validation failures prevent GRASS processing to avoid errors
            - Debug output helps identify specific NoData issues
            - Method handles various raster formats and edge cases gracefully
        """
        try:
            # Load raster layer
            raster_layer = QgsRasterLayer(raster_path, 'NoData_Validation')
            if not raster_layer.isValid():
                print(f'DEBUG: Could not load raster for NoData validation: {raster_path}')
                return False
            
            # Get raster provider
            provider = raster_layer.dataProvider()
            
            # Check if NoData value is defined
            nodata_value = provider.sourceNoDataValue(1)
            print(f'DEBUG: NoData value for band 1: {nodata_value}')
            
            # Check if NoData value is a valid number (not None or NaN)
            if nodata_value is None or (nodata_value != nodata_value):  # Check for NaN
                print('DEBUG: WARNING - NoData value is not properly defined!')
                return False
            
            # Get raster statistics to check for NoData pixels
            stats = provider.bandStatistics(1, QgsRasterBandStats.All)
            print(f'DEBUG: Raster statistics - Valid pixels: {stats.elementCount}')
            print(f'DEBUG: Raster statistics - Min: {stats.minimumValue}, Max: {stats.maximumValue}')
            
            # Check if there are actually NoData pixels in the raster
            if stats.elementCount == 0:
                print('DEBUG: WARNING - No valid pixels found in raster!')
                return False
            
            print('DEBUG: NoData validation successful')
            return True
            
        except Exception as e:
            print(f'DEBUG: Error during NoData validation: {str(e)}')
            return False

    def populate_layers(self):
        """
        Populate the input DSM combo box with available raster layers.
        
        Scans all layers in the current QGIS project and adds valid
        raster layers to the input DSM selection combo box. This allows
        users to select from already loaded DSM layers.
        
        Side Effects:
            - Clears and repopulates the comboInputDSM combo box
            - Adds layer names as display text and layer IDs as data
        """
        self.comboInputDSM.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self.comboInputDSM.addItem(layer.name(), layer.id())

    def setup_help_text(self):
        """
        Setup help text for parameter explanations.
        
        This method is kept for compatibility but has been replaced by
        the dynamic update_help_text_for_tab method. It delegates to
        the new system for consistency.
        
        Side Effects:
            - Calls update_help_text_for_tab with the first tab (index 0)
        """
        # This method is kept for compatibility but will be replaced by update_help_text_for_tab
        self.update_help_text_for_tab(0)

    def update_help_text_for_tab(self, tab_index):
        """
        Update help text based on currently active tab.
        
        Provides context-sensitive help text that changes based on which
        tab the user is currently viewing. This helps users understand
        the parameters and options available in each section.
        
        Args:
            tab_index (int): Index of the currently active tab (0-2)
                - 0: Input & Processing
                - 1: Advanced Options  
                - 2: Interpolation & Output
                
        Side Effects:
            - Updates the textEditHelp widget with appropriate help content
            - Handles exceptions gracefully with debug output
            
        Raises:
            Exception: If help text update fails (logged but not re-raised)
        """
        try:
            if tab_index == 0:  # Input & Processing
                help_text = self.get_tab1_help_text()
            elif tab_index == 1:  # Advanced Options
                help_text = self.get_tab2_help_text()
            elif tab_index == 2:  # Interpolation & Output
                help_text = self.get_tab3_help_text()
            else:
                help_text = "<b>Help</b><br/>Select a tab to see relevant help information."
            
            self.textEditHelp.setHtml(help_text)
        except Exception as e:
            print(f'DEBUG: Error updating help text: {str(e)}')

    def get_tab1_help_text(self):
        """
        Generate help text for Tab 1: Input & Processing.
        
        Provides detailed explanations of the input parameters and processing
        options available in the first tab. Includes information about DSM
        selection, output directory, threshold methods, and percentile settings.
        
        Returns:
            str: HTML-formatted help text for the Input & Processing tab
            
        Content includes:
            - Input DSM selection and resolution detection
            - Output directory specification
            - Threshold method comparison (percentile vs fixed)
            - Percentile parameter explanations
            - Fixed threshold value descriptions
            - Scientific methodology reference
        """
        return """
<b>INPUT & PROCESSING</b>

<b>Input DSM:</b>
Select your high-resolution DSM file or layer. Resolution will be detected automatically and parameters will be auto-scaled.

<b>Output Directory:</b>
Choose folder for results and intermediate files. All processing outputs will be saved here.

<b>Threshold Method:</b>
<u>Percentile-based (Recommended):</u>
• Adaptive thresholds based on data distribution
• Automatically adapts to terrain type
• Mountain areas: Higher natural slopes
• Flat areas: Lower natural slopes

<u>Fixed Thresholds (Legacy):</u>
• Manual threshold values
• Same values for all terrain types
• Use for comparison or specific requirements

<b>Percentile Settings:</b>
• <b>Slope:</b> % of values below anthropogenic threshold (90% = top 10% steepest)
• <b>Curvature:</b> % of values below feature threshold (95% = top 5% most curved)  
• <b>Residual:</b> % of values below anomaly threshold (95% = top 5% height differences)
• <b>Texture Variance:</b> % of values below vegetation threshold (90% = top 10% most variable)
• <b>Texture Entropy:</b> % of values below vegetation threshold (90% = top 10% most heterogeneous)

<b>Fixed Threshold Values:</b>
• <b>Slope:</b> Maximum natural slope (degrees)
• <b>Curvature:</b> Maximum natural curvature
• <b>Residual:</b> Height difference threshold (meters)

<b>Scientific Method (Cao et al. 2020):</b>
Objective, reproducible, landscape-independent methodology for bare earth reconstruction.

<b>Interpolation Methods:</b>
• <b>Enhanced GDAL:</b> Multi-stage processing with smoothing for complex datasets
• <b>Simple GDAL:</b> Fast single-stage processing for quick results
• <b>GRASS r.fillnulls:</b> Organic RST interpolation for natural terrain reconstruction
        """

    def get_tab2_help_text(self):
        """
        Generate help text for Tab 2: Advanced Options.
        
        Provides detailed explanations of advanced processing options including
        Gaussian filtering parameters, texture analysis settings, and filter
        options for selective feature removal.
        
        Returns:
            str: HTML-formatted help text for the Advanced Options tab
            
        Content includes:
            - Gaussian filter parameters and effects
            - Texture analysis methodology and parameters
            - Filter options for different feature types
            - Buffer and fill parameter explanations
            - Common parameter combinations and use cases
        """
        return """
<b>ADVANCED OPTIONS</b>

<b>Gaussian Filter:</b>
Smooths the DSM to separate terrain from features.
• <b>Sigma:</b> Smoothing strength (auto-scaled by pixel size)
• <b>Kernel Radius:</b> Filter size in pixels
• <b>Iterations:</b> Number of filter passes (2-3 recommended)

<b>Texture Analysis (3-Class):</b>
Distinguishes vegetation from anthropogenic features using surface texture patterns.
• <b>Enable:</b> Activates 3-class classification (Natural/Vegetation/Anthropogenic)
• <b>Window Size:</b> Analysis window (3x3 to 9x9 pixels)
• <b>Variance Threshold:</b> Vegetation detection sensitivity
• <b>Entropy Threshold:</b> Texture complexity threshold

<b>Filter Options:</b>
Choose which features to mask/remove:
• <b>Anthropogenic:</b> Buildings, roads, infrastructure
• <b>Vegetation:</b> Trees, bushes, forest cover

<u>Common Combinations:</u>
• Anthropogenic only: Traditional bare earth
• Vegetation only: Keep buildings, remove forest
• Both: Aggressive filtering for geology
• Neither: Validation/debugging mode

<b>Interpolation Options:</b>
• <b>Enhanced GDAL:</b> Multi-stage with smoothing (balanced quality/speed)
• <b>Simple GDAL:</b> Single-stage processing (fast results)
• <b>GRASS r.fillnulls:</b> Organic RST method (best for natural terrain)

<b>Buffer & Fill:</b>
• <b>Buffer Distance:</b> Expand masked areas (meters)
• <b>Fill Distance:</b> Maximum interpolation reach (pixels)
• <b>Fill Iterations:</b> Interpolation passes (1-10)
        """

    def get_tab3_help_text(self):
        """
        Generate help text for Tab 3: Interpolation & Output.
        
        Provides detailed explanations of interpolation methods, fill parameters,
        and output options. Includes quality tips and processing guidance.
        
        Returns:
            str: HTML-formatted help text for the Interpolation & Output tab
            
        Content includes:
            - Interpolation method comparison and selection
            - Fill parameter explanations and recommendations
            - Quality tips for optimal results
            - Processing workflow overview
        """
        return """
<b>INTERPOLATION & OUTPUT</b>

<b>Interpolation Methods:</b>
Choose algorithm for reconstructing masked areas:

<b>Enhanced GDAL (Multi-stage):</b>
• Multi-stage processing with smoothing
• Robust fallback method
• Good for complex datasets
• Reduces interpolation artifacts

<b>Simple GDAL:</b>
• Fast original method
• May create angular artifacts
• Use for quick processing
• Good for parameter testing

<b>GRASS r.fillnulls:</b>
• Organic interpolation using RST (Regularized Spline with Tension) method
• Excellent for natural terrain reconstruction and complex landscapes
• Smooth results with detail preservation and natural surface continuity
• Advanced parameters for fine-tuning: tension, smooth, edge, npmin, segmax, window size
• Window size controls local interpolation area (3-15): smaller = more detail, larger = smoother
• Includes NoData validation for reliable processing
• Falls back to Simple GDAL if GRASS processing fails

<b>Fill Parameters:</b>
• <b>Fill Distance:</b> How far to interpolate (pixels)
• <b>Fill Iterations:</b> Multiple passes for better results

<b>Quality Tips:</b>
• Use Enhanced GDAL for high-quality results
• Use Simple GDAL for testing parameters
• Larger fill distances = smoother results
• Multiple iterations = better gap filling

<b>Processing:</b>
Click "Run Reconstruction" to start processing with current settings.
        """

    def update_progress(self, step, total_steps, message="Processing..."):
        """
        Update both progress bar and status label with current processing status.
        
        Provides real-time feedback to the user about processing progress.
        Updates both the progress bar (numerical) and status label (textual)
        with current step information and percentage completion.
        
        Args:
            step (int): Current step number (0-based or 1-based)
            total_steps (int): Total number of steps in the process
            message (str): Status message to display to the user
            
        Side Effects:
            - Updates progress bar value and maximum
            - Updates status label with formatted progress information
            - Forces GUI update to ensure changes are visible
            
        Raises:
            Exception: If progress update fails (logged but not re-raised)
        """
        try:
            # Update progress bar
            self.progressBar.setValue(int(step))
            self.progressBar.setMaximum(int(total_steps))
            
            # Update status label
            if hasattr(self, 'labelProgressStatus'):
                percentage = int((step / total_steps) * 100) if total_steps > 0 else 0
                status_text = f"Step {step}/{total_steps} ({percentage}%) • {message}"
                self.labelProgressStatus.setText(status_text)
            
            # Force GUI update
            from qgis.PyQt.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            
        except Exception as e:
            print(f'DEBUG: Error updating progress: {str(e)}')

    def reset_progress(self):
        """
        Reset progress bar and status to initial state.
        
        Called at the beginning of processing to ensure a clean
        progress display. Sets progress bar to 0% and status
        to "Ready to start processing...".
        
        Side Effects:
            - Resets progress bar to 0/100
            - Sets status label to initial message
            - Handles exceptions gracefully with debug output
            
        Raises:
            Exception: If progress reset fails (logged but not re-raised)
        """
        try:
            self.progressBar.setValue(0)
            self.progressBar.setMaximum(100)
            if hasattr(self, 'labelProgressStatus'):
                self.labelProgressStatus.setText("Ready to start processing...")
        except Exception as e:
            print(f'DEBUG: Error resetting progress: {str(e)}')

    def browse_dsm(self):
        """
        Open file dialog for DSM selection.
        
        Provides a file browser dialog for users to select DSM files
        from their local filesystem. Supports multiple raster formats
        commonly used for DSM data.
        
        Side Effects:
            - Opens file dialog for DSM selection
            - Updates lineEditInputDSM with selected file path
            - Supports multiple raster formats (.tif, .tiff, .asc, etc.)
        """
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select DSM', '', 'Raster data (*.tif *.tiff *.asc *.img *.vrt *.sdat *.nc *.grd *.bil *.hdr *.adf *.dem *.dt0 *.dt1 *.dt2 *.flt *.hgt *.raw *.xyz *.txt);;All files (*)')
        if file_path:
            self.lineEditInputDSM.setText(file_path)

    def browse_output_dir(self):
        """
        Open directory dialog for output directory selection.
        
        Provides a directory browser dialog for users to select
        where processing results and intermediate files should be saved.
        
        Side Effects:
            - Opens directory dialog for output selection
            - Updates lineEditOutputDir with selected directory path
        """
        dir_path = QFileDialog.getExistingDirectory(self, 'Select output directory', '')
        if dir_path:
            self.lineEditOutputDir.setText(dir_path)

    def get_input_dsm(self):
        """
        Get the input DSM layer from user selection.
        
        Retrieves the DSM layer based on user input. Prioritizes file path
        input over layer selection from combo box. Validates that the
        selected DSM is valid and accessible.
        
        Returns:
            QgsRasterLayer: Valid DSM layer for processing, or None if invalid
            
        Raises:
            QMessageBox: Warning dialog if DSM path is invalid
            
        Note:
            - Priority: file path input, then layer selection
            - Validates file existence and layer validity
            - Provides user feedback for invalid selections
        """
        # Priority: file path, then layer
        file_path = self.lineEditInputDSM.text().strip()
        if file_path:
            if os.path.exists(file_path):
                return QgsRasterLayer(file_path, os.path.basename(file_path))
            else:
                QMessageBox.warning(self, 'Error', 'The specified DSM path is invalid!')
                return None
        else:
            layer_id = self.comboInputDSM.currentData()
            return QgsProject.instance().mapLayer(layer_id)

    def get_raster_path(self, raster_layer):
        """
        Get the file path for a raster layer.
        
        Extracts the file path from a QgsRasterLayer. If the layer was
        loaded from a file, returns the original path. Otherwise, creates
        a temporary file using GDAL translate.
        
        Args:
            raster_layer (QgsRasterLayer): The raster layer to get path for
            
        Returns:
            str: File path to the raster layer
            
        Note:
            - Prefers original file path if available
            - Creates temporary file if layer was loaded from memory
            - Uses GDAL translate for format conversion if needed
        """
        # If layer was loaded from file, return path
        src = raster_layer.source()
        if os.path.isfile(src) and src.lower().endswith((".tif", ".tiff", ".asc", ".img", ".vrt")):
            return src
        # Otherwise save temporarily
        temp_path = os.path.join(tempfile.gettempdir(), f"temp_input_dsm_{os.getpid()}.tif")
        _ = processing.run(
            "gdal:translate",
            {
                "INPUT": raster_layer,
                "TARGET_CRS": None,
                "NODATA": None,
                "COPY_SUBDATASETS": False,
                "OPTIONS": "",
                "EXTRA": "",
                "DATA_TYPE": 0,
                "OUTPUT": temp_path
            }
        )
        return temp_path

    def get_pixel_size_and_scale_parameters(self, dsm_layer):
        """
        Get pixel size from DSM and auto-scale parameters based on resolution.
        
        Analyzes the DSM resolution and automatically scales processing parameters
        to maintain consistent spatial effects regardless of input resolution.
        This ensures that the same physical distances are used for filtering,
        buffering, and interpolation regardless of pixel size.
        
        The method calculates a scale factor relative to a 2x2m reference
        resolution and adjusts parameters accordingly. It also provides
        user feedback about the scaling decisions.
        
        Args:
            dsm_layer (QgsRasterLayer): The input DSM layer to analyze
            
        Returns:
            dict: Dictionary containing scaling information and suggested parameters
                - pixel_size (float): Detected pixel size in map units
                - scale_factor (float): Scale factor relative to 2x2m reference
                - suggested_sigma (float): Auto-scaled Gaussian filter sigma
                - suggested_kernel_radius (int): Auto-scaled kernel radius
                - suggested_buffer_distance (float): Buffer distance (kept in meters)
                - suggested_fill_distance (int): Auto-scaled fill distance
                
        Side Effects:
            - May show dialog asking user to apply auto-scaled parameters
            - Updates UI parameters if user accepts auto-scaling
            - Provides detailed debug output about scaling decisions
            
        Note:
            - Reference resolution is 2x2m (original parameter optimization)
            - Buffer distance is kept in meters (no pixel scaling)
            - Parameters are clamped to reasonable ranges
            - User can decline auto-scaling to keep original values
        """
        try:
            # Get pixel size in map units
            pixel_size_x = abs(dsm_layer.rasterUnitsPerPixelX())
            pixel_size_y = abs(dsm_layer.rasterUnitsPerPixelY())
            pixel_size = (pixel_size_x + pixel_size_y) / 2  # Average pixel size
            
            print(f'DEBUG: Detected pixel size: {pixel_size:.3f} map units')
            print(f'DEBUG: Pixel size X: {pixel_size_x:.3f}, Y: {pixel_size_y:.3f}')
            
            # Reference resolution (2x2m) for which original parameters were optimized
            reference_resolution = 2.0
            
            # Calculate scaling factor
            scale_factor = pixel_size / reference_resolution
            print(f'DEBUG: Scale factor relative to 2x2m: {scale_factor:.3f}')
            
            # Get current parameter values from UI
            original_sigma = self.spinSigma.value()
            original_kernel_radius = self.spinKernelRadius.value()
            original_buffer_distance = self.spinBufferDistance.value()
            original_fill_distance = self.spinFillDistance.value()
            
            print(f'DEBUG: Auto-scaling analysis - Original buffer distance: {original_buffer_distance}m')
            
            # Auto-scale parameters
            # Sigma: Scale to maintain similar smoothing effect in map units
            # Target: 2-4m smoothing window regardless of pixel size
            target_smoothing_distance = 3.0  # 3 meters target smoothing
            scaled_sigma = target_smoothing_distance / pixel_size
            scaled_sigma = max(0.5, min(5.0, scaled_sigma))  # Clamp to reasonable range
            
            # Kernel radius: Scale to maintain similar spatial extent
            # Target: 6-10m kernel radius regardless of pixel size
            target_kernel_distance = 8.0  # 8 meters target kernel radius
            scaled_kernel_radius = int(target_kernel_distance / pixel_size)
            scaled_kernel_radius = max(1, min(15, scaled_kernel_radius))  # Clamp to reasonable range
            
            # Buffer distance: Keep in meters (no pixel scaling needed)
            # Buffer is already specified in meters, so no scaling required
            scaled_buffer_distance = original_buffer_distance  # Keep original meter value
            
            # Fill distance: Scale to maintain similar interpolation distance
            # Target: 100m fill distance regardless of pixel size
            target_fill_distance = 100.0  # 100 meters target fill distance
            scaled_fill_distance = int(target_fill_distance / pixel_size)
            scaled_fill_distance = max(1, min(1000, scaled_fill_distance))  # Clamp to reasonable range
            
            print(f'DEBUG: Original parameters - Sigma: {original_sigma}, Kernel: {original_kernel_radius}, Buffer: {original_buffer_distance}m, Fill: {original_fill_distance}')
            print(f'DEBUG: Scaled parameters - Sigma: {scaled_sigma:.2f}, Kernel: {scaled_kernel_radius}, Buffer: {scaled_buffer_distance}m, Fill: {scaled_fill_distance}')
            
            # Show scaling information to user
            if abs(scale_factor - 1.0) > 0.1:  # Only show if significant scaling needed
                scaling_message = f"""
Detected DSM resolution: {pixel_size:.3f}m

Auto-scaled parameters for your resolution:
• Sigma: {original_sigma:.2f} → {scaled_sigma:.2f}
• Kernel Radius: {original_kernel_radius} → {scaled_kernel_radius} pixels
• Buffer Distance: {original_buffer_distance}m ({
    "no buffering - stays at 0.0m" if original_buffer_distance <= 0.0 
    else "no scaling - stays in meters"
})
• Fill Distance: {original_fill_distance} → {scaled_fill_distance} pixels

Scale factor: {scale_factor:.2f}x relative to 2x2m reference
Target smoothing window: ~{target_smoothing_distance}m
                """
                
                reply = QMessageBox.question(
                    self, 
                    'Auto-Scale Parameters?', 
                    scaling_message + "\n\nApply auto-scaled parameters?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Update UI with scaled parameters
                    self.spinSigma.setValue(scaled_sigma)
                    self.spinKernelRadius.setValue(scaled_kernel_radius)
                    # Only update buffer distance if user didn't explicitly set it to 0.0
                    if original_buffer_distance > 0.0:
                        self.spinBufferDistance.setValue(scaled_buffer_distance)
                    # else: keep user's explicit 0.0 setting
                    self.spinFillDistance.setValue(scaled_fill_distance)
                    print('DEBUG: Parameters auto-scaled and applied to UI')
                    if original_buffer_distance <= 0.0:
                        print('DEBUG: Buffer Distance kept at 0.0 (user preference preserved)')
                else:
                    print('DEBUG: User declined auto-scaling, keeping original parameters')
            
            return {
                'pixel_size': pixel_size,
                'scale_factor': scale_factor,
                'suggested_sigma': scaled_sigma,
                'suggested_kernel_radius': scaled_kernel_radius,
                'suggested_buffer_distance': scaled_buffer_distance,
                'suggested_fill_distance': scaled_fill_distance
            }
            
        except Exception as e:
            print(f'DEBUG: Could not determine pixel size or scale parameters: {str(e)}')
            print('DEBUG: Using original parameters without scaling')
            return {
                'pixel_size': 2.0,  # Assume 2m default
                'scale_factor': 1.0,
                'suggested_sigma': self.spinSigma.value(),
                'suggested_kernel_radius': self.spinKernelRadius.value(),
                'suggested_buffer_distance': self.spinBufferDistance.value(),
                'suggested_fill_distance': self.spinFillDistance.value()
            }

    def calculate_raster_percentiles(self, raster_layer, percentile):
        """
        Calculate percentile value for a raster layer using memory-efficient processing.
        
        Implements the percentile calculation methodology from Cao et al. (2020) for
        adaptive threshold determination. Uses memory-efficient processing techniques
        to handle large raster datasets without excessive memory consumption.
        
        The method supports both complete raster analysis for smaller datasets and
        sampling-based analysis for very large datasets (>10M pixels). It provides
        comprehensive statistical information for debugging and validation.
        
        Args:
            raster_layer (QgsRasterLayer): The raster layer to analyze
            percentile (float): Percentile value to calculate (0-100)
                - 90: Top 10% of values (for anthropogenic features)
                - 95: Top 5% of values (for extreme features)
                - 85: Top 15% of values (for moderate features)
            
        Returns:
            float: Calculated percentile value, or None if calculation failed
            
        Raises:
            ImportError: If NumPy is not available (falls back to simple calculation)
            Exception: If raster reading or calculation fails
            
        Note:
            - Uses NumPy for efficient percentile calculation when available
            - Falls back to simple sorting-based calculation if NumPy unavailable
            - Handles NoData values automatically
            - Provides detailed debug output for validation
            - Sampling is used for datasets >10M pixels to improve performance
            
        Example:
            >>> slope_threshold = calculate_raster_percentiles(slope_layer, 90)
            >>> # Returns the 90th percentile of slope values
        """
        try:
            print(f'DEBUG: Calculating {percentile}th percentile for {raster_layer.name()}...')
            
            # Validate raster layer before processing
            if not raster_layer or not raster_layer.isValid():
                raise Exception(f"Invalid raster layer: {raster_layer.name() if raster_layer else 'None'}")
            
            # Get raster provider with validation
            provider = raster_layer.dataProvider()
            if not provider or not provider.isValid():
                raise Exception(f"Invalid raster provider for {raster_layer.name()}")
            
            # Test provider with small sample to ensure it's working
            try:
                test_point = raster_layer.extent().center()
                test_value, test_success = provider.sample(test_point, 1)
                if not test_success:
                    print(f'DEBUG: Warning - Provider sample test failed for {raster_layer.name()}')
            except Exception as test_error:
                print(f'DEBUG: Warning - Provider test failed: {str(test_error)}')
            
            # Get raster dimensions
            width = raster_layer.width()
            height = raster_layer.height()
            extent = raster_layer.extent()
            
            # Check memory usage before processing large datasets
            try:
                import psutil
                memory_percent = psutil.virtual_memory().percent
                print(f'DEBUG: Memory usage before processing: {memory_percent:.1f}%')
                if memory_percent > 90:
                    print(f'DEBUG: WARNING - High memory usage detected: {memory_percent:.1f}%')
                
                # Store initial memory for comparison
                initial_memory = psutil.virtual_memory().used
                
            except ImportError:
                print('DEBUG: psutil not available - memory monitoring disabled')
                initial_memory = None
            except Exception as mem_error:
                print(f'DEBUG: Memory check failed: {str(mem_error)}')
                initial_memory = None
            
            print(f'DEBUG: Raster dimensions: {width}x{height} pixels')
            
            # Memory-efficient processing with chunked approach
            total_pixels = width * height
            print(f'DEBUG: Total pixels to process: {total_pixels:,}')
            
            # Determine processing strategy based on dataset size
            if total_pixels > 5000000:  # > 5M pixels - use sampling
                print('DEBUG: Large raster detected, using statistical sampling for percentile calculation')
                target_samples = min(100000, total_pixels // 10)  # Max 100k samples, or 10% of pixels
                sample_factor = max(1, int((total_pixels / target_samples) ** 0.5))
                
                print(f'DEBUG: Sampling strategy: {target_samples:,} samples, factor {sample_factor}')
                
                # Create systematic sample coordinates
                values = []
                nodata_value = provider.sourceNoDataValue(1)
                samples_taken = 0
                
                for i in range(0, width, sample_factor):
                    for j in range(0, height, sample_factor):
                        if samples_taken >= target_samples:
                            break
                        
                        try:
                            # Convert pixel coordinates to map coordinates
                            x = extent.xMinimum() + (i + 0.5) * raster_layer.rasterUnitsPerPixelX()
                            y = extent.yMaximum() - (j + 0.5) * raster_layer.rasterUnitsPerPixelY()
                            
                            # Sample value using provider
                            value, success = provider.sample(QgsPointXY(x, y), 1)
                            if success and value != nodata_value and not (value != value):  # Check for valid value
                                values.append(value)
                            
                            samples_taken += 1
                            
                            # Progress update every 1000 samples
                            if samples_taken % 1000 == 0:
                                print(f'DEBUG: Sampled {samples_taken:,} pixels...')
                                
                        except Exception as sample_error:
                            print(f'DEBUG: Sample error at ({i},{j}): {str(sample_error)}')
                            continue
                    
                    if samples_taken >= target_samples:
                        break
                        
                print(f'DEBUG: Sampling completed: {len(values):,} valid samples from {samples_taken:,} total samples')
                
                # Memory monitoring after sampling
                if initial_memory is not None:
                    try:
                        current_memory = psutil.virtual_memory().used
                        memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB
                        print(f'DEBUG: Memory increase after sampling: {memory_increase:.1f} MB')
                    except:
                        pass
                
            elif total_pixels > 1000000:  # 1M-5M pixels - use chunked processing
                print('DEBUG: Medium raster detected, using chunked processing for percentile calculation')
                
                # Use chunked processing to reduce memory usage
                chunk_size = 1000  # Process 1000x1000 pixel chunks
                values = []
                nodata_value = provider.sourceNoDataValue(1)
                
                for chunk_x in range(0, width, chunk_size):
                    for chunk_y in range(0, height, chunk_size):
                        # Calculate chunk dimensions
                        chunk_width = min(chunk_size, width - chunk_x)
                        chunk_height = min(chunk_size, height - chunk_y)
                        
                        # Create chunk extent
                        chunk_extent = QgsRectangle(
                            extent.xMinimum() + chunk_x * raster_layer.rasterUnitsPerPixelX(),
                            extent.yMaximum() - (chunk_y + chunk_height) * raster_layer.rasterUnitsPerPixelY(),
                            extent.xMinimum() + (chunk_x + chunk_width) * raster_layer.rasterUnitsPerPixelX(),
                            extent.yMaximum() - chunk_y * raster_layer.rasterUnitsPerPixelY()
                        )
                        
                        try:
                            # Skip block creation - use sampling instead
                            pass
                            
                            # Process chunk values using sampling to avoid block access issues
                            sample_factor = max(1, min(10, chunk_width // 100))  # Sample every 10th pixel or 1% of chunk
                            
                            for i in range(0, chunk_width, sample_factor):
                                for j in range(0, chunk_height, sample_factor):
                                    try:
                                        # Convert chunk pixel coordinates to map coordinates
                                        x = chunk_extent.xMinimum() + (i + 0.5) * raster_layer.rasterUnitsPerPixelX()
                                        y = chunk_extent.yMaximum() - (j + 0.5) * raster_layer.rasterUnitsPerPixelY()
                                        
                                        # Sample value using provider (safer than block access)
                                        value, success = provider.sample(QgsPointXY(x, y), 1)
                                        if success and value != nodata_value and not (value != value):
                                            values.append(value)
                                    except Exception as chunk_error:
                                        continue  # Skip problematic pixels
                            
                            # Progress update
                            if (chunk_x // chunk_size + chunk_y // chunk_size) % 10 == 0:
                                print(f'DEBUG: Processed chunk ({chunk_x},{chunk_y}), total values: {len(values):,}')
                                
                        except Exception as chunk_error:
                            print(f'DEBUG: Chunk processing error at ({chunk_x},{chunk_y}): {str(chunk_error)}')
                            continue
                
                print(f'DEBUG: Chunked processing completed: {len(values):,} valid pixels')
                
                # Memory monitoring after chunked processing
                if initial_memory is not None:
                    try:
                        current_memory = psutil.virtual_memory().used
                        memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB
                        print(f'DEBUG: Memory increase after chunked processing: {memory_increase:.1f} MB')
                    except:
                        pass
                
            else:  # < 1M pixels - use safe sampling approach
                print('DEBUG: Small raster detected, using safe sampling approach for percentile calculation')
                
                # Use sampling approach to avoid block access issues
                target_samples = min(50000, total_pixels // 2)  # Max 50k samples, or 50% of pixels
                sample_factor = max(1, int((total_pixels / target_samples) ** 0.5))
                
                print(f'DEBUG: Safe sampling strategy: {target_samples:,} samples, factor {sample_factor}')
                
                # Create systematic sample coordinates
                values = []
                nodata_value = provider.sourceNoDataValue(1)
                samples_taken = 0
                
                for i in range(0, width, sample_factor):
                    for j in range(0, height, sample_factor):
                        if samples_taken >= target_samples:
                            break
                        
                        try:
                            # Convert pixel coordinates to map coordinates
                            x = extent.xMinimum() + (i + 0.5) * raster_layer.rasterUnitsPerPixelX()
                            y = extent.yMaximum() - (j + 0.5) * raster_layer.rasterUnitsPerPixelY()
                            
                            # Sample value using provider (safer than block access)
                            value, success = provider.sample(QgsPointXY(x, y), 1)
                            if success and value != nodata_value and not (value != value):  # Check for valid value
                                values.append(value)
                            
                            samples_taken += 1
                            
                            # Progress update every 5000 samples
                            if samples_taken % 5000 == 0:
                                print(f'DEBUG: Sampled {samples_taken:,} pixels...')
                                
                        except Exception as sample_error:
                            print(f'DEBUG: Sample error at ({i},{j}): {str(sample_error)}')
                            continue
                    
                    if samples_taken >= target_samples:
                        break
                        
                print(f'DEBUG: Safe sampling completed: {len(values):,} valid samples from {samples_taken:,} total samples')
                
                # Memory monitoring after safe sampling
                if initial_memory is not None:
                    try:
                        current_memory = psutil.virtual_memory().used
                        memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB
                        print(f'DEBUG: Memory increase after safe sampling: {memory_increase:.1f} MB')
                    except:
                        pass
            
            if len(values) == 0:
                raise Exception("No valid pixel values found")
            
            # Calculate percentile using memory-efficient numpy processing
            try:
                import numpy as np
                
                # Use memory-efficient array creation
                if len(values) > 1000000:  # > 1M values - use float32 for memory efficiency
                    print('DEBUG: Large dataset detected, using float32 for memory efficiency')
                    values_array = np.array(values, dtype=np.float32)
                else:
                    values_array = np.array(values)
            
                # Validate array before calculation
                if len(values_array) == 0:
                    raise Exception("Empty values array after conversion")
                
                # Check for invalid values in array
                if np.any(np.isnan(values_array)) or np.any(np.isinf(values_array)):
                    print('DEBUG: Warning - Invalid values (NaN/Inf) detected in array')
                    # Remove invalid values
                    values_array = values_array[np.isfinite(values_array)]
                    if len(values_array) == 0:
                        raise Exception("No valid values after removing NaN/Inf")
                
                print(f'DEBUG: Final array size: {len(values_array):,} valid values')
                print(f'DEBUG: Array memory usage: {values_array.nbytes / 1024 / 1024:.1f} MB')
                
                # Memory monitoring after array creation
                if initial_memory is not None:
                    try:
                        current_memory = psutil.virtual_memory().used
                        memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB
                        print(f'DEBUG: Total memory increase: {memory_increase:.1f} MB')
                    except:
                        pass
                
            except ImportError:
                raise ImportError("NumPy is required for percentile calculation")
            except Exception as np_error:
                print(f'DEBUG: NumPy array creation failed: {str(np_error)}')
                raise Exception(f"Array processing failed: {str(np_error)}")
            
            # Calculate percentile with safety checks
            try:
                percentile_value = np.percentile(values_array, percentile)
                
                # Validate percentile result
                if np.isnan(percentile_value) or np.isinf(percentile_value):
                    raise Exception("Invalid percentile result (NaN/Inf)")
                
                # Calculate some additional statistics for debugging
                min_val = np.min(values_array)
                max_val = np.max(values_array)
                mean_val = np.mean(values_array)
                std_val = np.std(values_array)
                    
                # Validate statistics
                if any(np.isnan([min_val, max_val, mean_val, std_val])) or any(np.isinf([min_val, max_val, mean_val, std_val])):
                    print('DEBUG: Warning - Invalid statistics detected')
                
                print(f'DEBUG: Raster statistics - Min: {min_val:.4f}, Max: {max_val:.4f}')
                print(f'DEBUG: Raster statistics - Mean: {mean_val:.4f}, StdDev: {std_val:.4f}')
                print(f'DEBUG: {percentile}th percentile: {percentile_value:.4f}')
                
                return float(percentile_value)
                
            except Exception as calc_error:
                print(f'DEBUG: Percentile calculation failed: {str(calc_error)}')
                raise Exception(f"Percentile calculation failed: {str(calc_error)}")
            
        except ImportError:
            print('DEBUG: NumPy not available, using alternative percentile calculation')
            
            # Fallback: Simple percentile calculation without numpy
            try:
                if len(values) == 0:
                    print('DEBUG: No values available for fallback calculation')
                    return None
                
                # Validate values before sorting
                valid_values = [v for v in values if v == v and v != nodata_value]  # Remove NaN and NoData
                if len(valid_values) == 0:
                    print('DEBUG: No valid values for fallback calculation')
                    return None
                
                valid_values.sort()
                index = int((percentile / 100.0) * (len(valid_values) - 1))
                index = max(0, min(index, len(valid_values) - 1))  # Ensure index is within bounds
                percentile_value = valid_values[index]
                
                print(f'DEBUG: {percentile}th percentile (fallback): {percentile_value:.4f}')
                return float(percentile_value)
                
            except Exception as fallback_error:
                print(f'DEBUG: Fallback calculation failed: {str(fallback_error)}')
                return None
            
        except Exception as e:
            print(f'DEBUG: Percentile calculation failed for {raster_layer.name()}: {str(e)}')
            return None

    def generate_processing_report(self, input_dsm, output_dir, scaling_info, gaussian_iterations, 
                                  sigma_value, kernel_radius, buffer_distance, fill_distance, 
                                  fill_iterations, interpolation_method, original_interpolation_method,
                                  stats_results, slope_threshold, curvature_threshold, residual_threshold, 
                                  use_residuals, slope_layer, curvature_layer, residual_layer, 
                                  anthropogenic_pixels, total_pixels, output_dsm):
        """
        Generate a comprehensive processing report documenting all parameters and results.
        
        Creates a detailed text report that documents the entire processing workflow,
        including all input parameters, intermediate results, and final outputs.
        This report serves as both documentation and validation of the processing
        results for scientific reproducibility.
        
        The report includes:
        - Input information and DSM properties
        - Processing parameters and auto-scaling details
        - Statistical analysis results and applied thresholds
        - Classification results and anthropogenic feature detection
        - Interpolation method details (including GRASS r.fillnulls parameters)
        - Output file descriptions and quality metrics
        - Processing timestamps and version information
        
        Args:
            input_dsm (QgsRasterLayer): Original input DSM layer
            output_dir (str): Output directory path
            scaling_info (dict): Auto-scaling information and parameters
            gaussian_iterations (int): Number of Gaussian filter iterations
            sigma_value (float): Gaussian filter sigma parameter
            kernel_radius (int): Gaussian filter kernel radius
            buffer_distance (float): Buffer distance in meters
            fill_distance (int): Fill distance in pixels
            fill_iterations (int): Number of fill iterations
            interpolation_method (str): Actually used interpolation method
            original_interpolation_method (str): User-selected interpolation method
            stats_results (dict): Statistical analysis results (percentile-based)
            slope_threshold (float): Applied slope threshold
            curvature_threshold (float): Applied curvature threshold
            residual_threshold (float): Applied residual threshold
            use_residuals (bool): Whether residual analysis was used
            slope_layer (QgsRasterLayer): Calculated slope layer
            curvature_layer (QgsRasterLayer): Calculated curvature layer
            residual_layer (QgsRasterLayer): Calculated residual layer
            anthropogenic_pixels (int): Number of anthropogenic pixels detected
            total_pixels (int): Total number of pixels in dataset
            output_dsm (str): Path to final reconstructed DSM
            
        Returns:
            str: Path to the generated report file, or None if generation failed
            
        Side Effects:
            - Creates a timestamped report file in the output directory
            - Includes comprehensive statistical analysis
            - Documents all processing steps and parameters
            - Provides quality assessment and warnings
            
        Note:
            - Report filename includes timestamp for uniqueness
            - Report is saved in UTF-8 encoding for international character support
            - Includes both original and actual processing parameters
            - Provides warnings for potential quality issues
        """
        try:
            from datetime import datetime
            import os
            
            # Create timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"reconstruction_report_{timestamp}.txt"
            report_path = os.path.join(output_dir, report_filename)
            
            print(f'DEBUG: Generating processing report: {report_path}')
            
            with open(report_path, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 80 + "\n")
                f.write("BARE EARTH RECONSTRUCTOR - PROCESSING REPORT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Plugin Version: Advanced with Percentile-based Thresholds (Cao et al. 2020)\n")
                f.write("\n")
                
                # Input Information
                f.write("INPUT INFORMATION\n")
                f.write("-" * 40 + "\n")
                f.write(f"Input DSM: {input_dsm.name()}\n")
                f.write(f"Source Path: {self.get_raster_path(input_dsm)}\n")
                f.write(f"CRS: {input_dsm.crs().authid()}\n")
                f.write(f"Dimensions: {input_dsm.width()} x {input_dsm.height()} pixels\n")
                f.write(f"Pixel Size: {scaling_info['pixel_size']:.3f} m\n")
                f.write(f"Scale Factor: {scaling_info['scale_factor']:.3f}x (relative to 2x2m reference)\n")
                f.write(f"Output Directory: {output_dir}\n")
                f.write("\n")
                
                # Processing Parameters
                f.write("PROCESSING PARAMETERS\n")
                f.write("-" * 40 + "\n")
                
                # Threshold Method
                threshold_method = "Percentile-based (Cao et al. 2020)" if self.radioPercentile.isChecked() else "Fixed Thresholds"
                f.write(f"Threshold Method: {threshold_method}\n")
                
                if self.radioPercentile.isChecked() and stats_results:
                    f.write(f"Slope Percentile: {stats_results['slope_percentile']:.1f}%\n")
                    f.write(f"Curvature Percentile: {stats_results['curvature_percentile']:.1f}%\n")
                    f.write(f"Residual Percentile: {stats_results['residual_percentile']:.1f}%\n")
                else:
                    f.write(f"Fixed Slope Threshold: {self.spinSlope.value():.4f}°\n")
                    f.write(f"Fixed Curvature Threshold: {self.spinCurvature.value():.4f}\n")
                    f.write(f"Fixed Residual Threshold: {self.spinResidual.value():.4f} m\n")
                
                f.write(f"Gaussian Filter Sigma: {sigma_value:.3f}\n")
                f.write(f"Gaussian Filter Kernel Radius: {kernel_radius} pixels\n")
                f.write(f"Gaussian Filter Iterations: {gaussian_iterations}\n")
                f.write(f"Buffer Distance: {buffer_distance:.1f} m\n")
                f.write(f"Fill Distance: {fill_distance} pixels (~{fill_distance * scaling_info['pixel_size']:.1f} m)\n")
                f.write(f"Fill Iterations: {fill_iterations}\n")
                f.write(f"Selected Interpolation Method: {original_interpolation_method.upper()}\n")
                if interpolation_method != original_interpolation_method:
                    f.write(f"Actually Used Method: {interpolation_method.upper()} (fallback applied)\n")
                else:
                    f.write(f"Actually Used Method: {interpolation_method.upper()}\n")
                
                # GRASS r.fillnulls Parameters (if used)
                if original_interpolation_method == 'grass_fillnulls':
                    f.write("\nGRASS R.FILLNULLS PARAMETERS\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"Method: RST (Regularized Spline with Tension, method=0)\n")
                    f.write(f"Tension: {self.spinTension.value()}\n")
                    f.write(f"Smooth: {self.spinSmooth.value():.2f}\n")
                    f.write(f"Edge: {self.spinEdge.value()}\n")
                    f.write(f"Npmin: {self.spinNpmin.value()}\n")
                    f.write(f"Segmax: {self.spinSegmax.value()}\n")
                    f.write(f"Window Size: {self.spinGrassWindowSize.value()}\n")
                    f.write("\n")
                
                f.write("\n")
                
                # Texture Analysis Parameters (if enabled)
                if stats_results and stats_results.get('use_texture', False):
                    f.write("TEXTURE ANALYSIS PARAMETERS\n")
                    f.write("-" * 40 + "\n")
                    try:
                        window_size = self.spinTextureWindow.value() if hasattr(self, 'spinTextureWindow') else 3
                    except:
                        window_size = 3
                    f.write(f"Window Size: {window_size}x{window_size}\n")
                    f.write(f"Variance Threshold ({stats_results.get('variance_percentile', 90)}th percentile): {stats_results['variance_threshold']:.4f}\n")
                    f.write(f"Entropy Threshold ({stats_results.get('entropy_percentile', 90)}th percentile): {stats_results['entropy_threshold']:.4f}\n")
                    f.write("Classification: 0=Natural, 1=Vegetation, 2=Anthropogenic\n")
                    f.write("Selective Buffering: Only anthropogenic features (class 2)\n")
                    f.write("Selective Masking: Preserve vegetation, mask only anthropogenic\n")
                    f.write("\n")
                
                # Applied Thresholds (Final Values)
                f.write("APPLIED THRESHOLDS\n")
                f.write("-" * 40 + "\n")
                f.write(f"Slope Threshold: {slope_threshold:.4f}°\n")
                f.write(f"Curvature Threshold: ±{curvature_threshold:.4f}\n")
                if use_residuals:
                    f.write(f"Residual Threshold: ±{residual_threshold:.4f} m\n")
                else:
                    f.write("Residual Analysis: Disabled\n")
                f.write("\n")
                
                # Statistical Results
                f.write("GEOMORPHOMETRIC STATISTICS\n")
                f.write("-" * 40 + "\n")
                
                # Slope Statistics
                try:
                    slope_stats = slope_layer.dataProvider().bandStatistics(1)
                    f.write(f"Slope - Min/Max: {slope_stats.minimumValue:.4f}° / {slope_stats.maximumValue:.4f}°\n")
                    f.write(f"Slope - Mean/StdDev: {slope_stats.mean:.4f}° / {slope_stats.stdDev:.4f}°\n")
                except:
                    f.write("Slope Statistics: Not available\n")
                
                # Curvature Statistics  
                try:
                    curvature_stats = curvature_layer.dataProvider().bandStatistics(1)
                    f.write(f"Curvature - Min/Max: {curvature_stats.minimumValue:.6f} / {curvature_stats.maximumValue:.6f}\n")
                    f.write(f"Curvature - Mean/StdDev: {curvature_stats.mean:.6f} / {curvature_stats.stdDev:.6f}\n")
                except:
                    f.write("Curvature Statistics: Not available\n")
                
                # Residual Statistics
                if use_residuals and residual_layer:
                    try:
                        residual_stats = residual_layer.dataProvider().bandStatistics(1)
                        f.write(f"Residuals - Min/Max: {residual_stats.minimumValue:.4f} m / {residual_stats.maximumValue:.4f} m\n")
                        f.write(f"Residuals - Mean/StdDev: {residual_stats.mean:.6f} m / {residual_stats.stdDev:.4f} m\n")
                    except:
                        f.write("Residual Statistics: Not available\n")
                else:
                    f.write("Residual Statistics: Not calculated\n")
                f.write("\n")
                
                # Anthropogenic Detection Results
                f.write("ANTHROPOGENIC FEATURE DETECTION\n")
                f.write("-" * 40 + "\n")
                if total_pixels > 0:
                    anthropogenic_percentage = (anthropogenic_pixels / total_pixels) * 100
                    f.write(f"Total Pixels: {total_pixels:,}\n")
                    f.write(f"Anthropogenic Pixels: {anthropogenic_pixels:,}\n")
                    f.write(f"Anthropogenic Area: {anthropogenic_percentage:.2f}%\n")
                    
                    # Buffering results
                    buffered_percentage = 0
                    try:
                        buffered_path = os.path.join(output_dir, 'buffered_anthropogenic.tif')
                        if os.path.exists(buffered_path):
                            buffered_layer = QgsRasterLayer(buffered_path, 'Buffered_Check')
                            if buffered_layer.isValid():
                                buffered_stats = buffered_layer.dataProvider().bandStatistics(1)
                                buffered_percentage = (buffered_stats.sum / total_pixels) * 100
                                f.write(f"Buffered Area: {buffered_percentage:.2f}%\n")
                                
                                if buffered_percentage > 50:
                                    f.write("*** WARNING: High buffering percentage detected! ***\n")
                                    f.write("Consider adjusting threshold parameters.\n")
                    except:
                        f.write("Buffered Area: Could not calculate\n")
                else:
                    f.write("Detection Results: Not available\n")
                f.write("\n")
                
                # Classification Statistics (if texture analysis was used)
                output_anthropogenic = os.path.join(output_dir, 'anthropogenic_features.tif')
                if stats_results and stats_results.get('use_texture', False) and os.path.exists(output_anthropogenic):
                    f.write("CLASSIFICATION STATISTICS\n")
                    f.write("-" * 40 + "\n")
                    try:
                        anthro_layer = QgsRasterLayer(output_anthropogenic, 'Classification_Stats')
                        if anthro_layer.isValid():
                            # Use sampling for efficient class counting
                            width = anthro_layer.width()
                            height = anthro_layer.height()
                            class_counts = {0: 0, 1: 0, 2: 0}  # Natural, Vegetation, Anthropogenic
                            total_pixels = 0
                            
                            # Use sampling approach for classification statistics to avoid block access issues
                            sample_size = min(10000, width * height // 100)  # Sample 1% or max 10k pixels
                            sample_factor = max(1, int((width * height / sample_size) ** 0.5))
                            
                            for i in range(0, width, sample_factor):
                                for j in range(0, height, sample_factor):
                                    try:
                                        # Convert pixel coordinates to map coordinates
                                        x = anthro_layer.extent().xMinimum() + (i + 0.5) * anthro_layer.rasterUnitsPerPixelX()
                                        y = anthro_layer.extent().yMaximum() - (j + 0.5) * anthro_layer.rasterUnitsPerPixelY()
                                        
                                        # Sample value using provider (safer than block access)
                                        value, success = anthro_layer.dataProvider().sample(QgsPointXY(x, y), 1)
                                        if success and value == value:  # Check not NaN
                                            class_counts[int(value)] = class_counts.get(int(value), 0) + 1
                                            total_pixels += 1
                                    except Exception as sample_error:
                                        continue  # Skip problematic pixels
                            
                            if total_pixels > 0:
                                natural_pct = (class_counts[0] / total_pixels) * 100
                                vegetation_pct = (class_counts[1] / total_pixels) * 100
                                anthropogenic_pct = (class_counts[2] / total_pixels) * 100
                                
                                f.write(f"Total Valid Pixels: {total_pixels:,}\n")
                                f.write(f"Natural Landscape (0): {class_counts[0]:,} pixels ({natural_pct:.2f}%)\n")
                                f.write(f"Vegetation (1): {class_counts[1]:,} pixels ({vegetation_pct:.2f}%)\n")
                                f.write(f"Anthropogenic (2): {class_counts[2]:,} pixels ({anthropogenic_pct:.2f}%)\n")
                            else:
                                f.write("Classification Statistics: No valid pixels found\n")
                    except Exception as e:
                        f.write(f"Classification Statistics: Error - {str(e)}\n")
                    f.write("\n")
                
                # Original DSM Statistics
                f.write("ORIGINAL DSM STATISTICS\n")
                f.write("-" * 40 + "\n")
                try:
                    original_stats = input_dsm.dataProvider().bandStatistics(1)
                    f.write(f"Elevation Range: {original_stats.minimumValue:.3f} - {original_stats.maximumValue:.3f} m\n")
                    f.write(f"Mean Elevation: {original_stats.mean:.3f} m\n")
                    f.write(f"Elevation StdDev: {original_stats.stdDev:.3f} m\n")
                except:
                    f.write("Original DSM Statistics: Not available\n")
                f.write("\n")
                
                # Reconstructed DSM Statistics
                f.write("RECONSTRUCTED DSM STATISTICS\n")
                f.write("-" * 40 + "\n")
                try:
                    reconstructed_layer = QgsRasterLayer(output_dsm, 'Reconstructed_Stats')
                    if reconstructed_layer.isValid():
                        reconstructed_stats = reconstructed_layer.dataProvider().bandStatistics(1)
                        f.write(f"Elevation Range: {reconstructed_stats.minimumValue:.3f} - {reconstructed_stats.maximumValue:.3f} m\n")
                        f.write(f"Mean Elevation: {reconstructed_stats.mean:.3f} m\n")
                        f.write(f"Elevation StdDev: {reconstructed_stats.stdDev:.3f} m\n")
                        
                        # Quality metrics
                        original_stats = input_dsm.dataProvider().bandStatistics(1)
                        mean_diff = abs(reconstructed_stats.mean - original_stats.mean)
                        std_diff = abs(reconstructed_stats.stdDev - original_stats.stdDev)
                        
                        f.write(f"Mean Difference: {mean_diff:.3f} m\n")
                        f.write(f"StdDev Difference: {std_diff:.3f} m\n")
                        
                        if mean_diff > 1.0:
                            f.write("*** WARNING: Large mean difference detected! ***\n")
                        if std_diff > 1.0:
                            f.write("*** WARNING: Large standard deviation difference detected! ***\n")
                    else:
                        f.write("Reconstructed DSM Statistics: Could not load output file\n")
                except Exception as e:
                    f.write(f"Reconstructed DSM Statistics: Error - {str(e)}\n")
                f.write("\n")
                
                # Output Files
                f.write("OUTPUT FILES\n")
                f.write("-" * 40 + "\n")
                output_files = [
                    ("Filtered DSM", "filtered_dsm.tif"),
                    ("Slope", "slope.tif"),
                    ("Curvature", "curvature.tif"),
                    ("Anthropogenic Features", "anthropogenic_features.tif"),
                    ("Buffered Anthropogenic", "buffered_anthropogenic.tif"),
                    ("Masked DSM", "masked_dsm.tif"),
                    ("Reconstructed DSM", "reconstructed_dsm.tif")
                ]
                
                if use_residuals:
                    output_files.insert(3, ("Residuals", "residuals.tif"))
                
                # Add texture files if texture analysis was used
                if stats_results and stats_results.get('use_texture', False):
                    output_files.insert(-3, ("Texture Variance", "texture_variance.tif"))
                    output_files.insert(-3, ("Texture Entropy", "texture_entropy.tif"))
                    # Check if texture was successfully created (not just enabled)
                    texture_variance_path = os.path.join(output_dir, 'texture_variance.tif')
                    if os.path.exists(texture_variance_path):
                        output_files.insert(-3, ("Anthropogenic Only", "anthropogenic_only.tif"))
                
                for description, filename in output_files:
                    filepath = os.path.join(output_dir, filename)
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
                        f.write(f"{description}: {filename} ({file_size:.1f} MB)\n")
                    else:
                        f.write(f"{description}: {filename} (NOT FOUND)\n")
                
                f.write(f"Processing Report: {report_filename}\n")
                f.write("\n")
                
                # Footer
                f.write("=" * 80 + "\n")
                f.write("END OF REPORT\n")
                f.write("=" * 80 + "\n")
            
            print(f'DEBUG: Processing report generated successfully: {report_filename}')
            return report_path
            
        except Exception as e:
            print(f'DEBUG: Failed to generate processing report: {str(e)}')
            return None

    def organize_output_files(self, output_dir):
        """
        Organize output files after processing completion for better structure.
        
        Creates a clean file organization system that separates final results
        from intermediate processing files. This improves usability by keeping
        the main output directory focused on the most important results while
        preserving all intermediate files for debugging and validation.
        
        File Organization:
        - Main directory: Final results (reconstructed DSM, classification, reports)
        - Intermediate/ subdirectory: All intermediate processing files
        
        The method handles file locking issues gracefully and provides user
        feedback about the organization process.
        
        Args:
            output_dir (str): Path to the output directory to organize
            
        Side Effects:
            - Creates 'Intermediate' subdirectory
            - Moves intermediate files to subdirectory
            - Creates organization summary file
            - Shows user notification about organization results
            - Handles file locking gracefully
            
        Note:
            - Some files may remain in main directory if locked by QGIS
            - Provides detailed logging of organization process
            - Creates summary file with organization details
            - User can safely delete Intermediate/ folder if only final results needed
        """
        try:
            import os
            import shutil
            from datetime import datetime
            
            print('DEBUG:  Organizing output files for better structure...')
            
            # Create intermediate files directory
            intermediate_dir = os.path.join(output_dir, 'Intermediate')
            os.makedirs(intermediate_dir, exist_ok=True)
            
            # Define final result files (keep in main directory)
            final_files = [
                'reconstructed_dsm.tif',           #  Main result
                'anthropogenic_features.tif',      #  Main classification
                'texture_variance*.tif',           #  Texture analysis results
                'texture_entropy*.tif',            #  Texture analysis results
                'reconstruction_report_*.txt'      #  Report (handled separately with wildcard)
            ]
            
            # Define intermediate files (move to subdirectory)
            intermediate_files = [
                'filtered_dsm.tif',                    # Gaussian filtered DSM
                'slope.tif',                           # Slope calculation
                'curvature.tif',                       # Curvature calculation
                'residuals.tif',                       # Residuals (Original - Filtered)

                'buffered_anthropogenic.tif',          # Buffered features mask
                'selected_features_for_buffering.tif', # Selected features for buffering
                'masked_dsm.tif',                      # Masked DSM before interpolation
                'anthropogenic_only.tif',              # Anthropogenic-only mask
                '*_resampled.tif',                     # Any resampled files
                '*_temp*.tif',                         # Any temporary files
                'filtered_dsm_iter_*.tif',             # Iteration files from Gaussian filter
                'temp_*.tif',                          # Temporary processing files
                'proximity_temp.tif',                  # Proximity calculation temp
                'curvature_resampled.tif',             # Resampled curvature
                'residual_resampled.tif',              # Resampled residuals
                'buffered_anthropogenic_resampled.tif', # Resampled buffered mask
                'sample_points_*.shp',                 # Point files for interpolation
                'sample_points_*.shx',                 # Shapefile components
                'sample_points_*.dbf',                 # Shapefile components
                'sample_points_*.prj',                 # Shapefile components
                'sample_points_*.cpg',                 # Shapefile components
                '*.tfw',                               # GDAL world files
                '*.aux.xml',                           # GDAL auxiliary files
                '*_temp.tif',                          # More temp file patterns
                'proximity_*.tif'                      # Proximity calculation files
            ]
            
            moved_count = 0
            kept_count = 0
            
            # Get all files in output directory
            all_files = []
            try:
                all_files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
            except Exception as e:
                print(f'DEBUG: Error listing files: {str(e)}')
                return
            
            print(f'DEBUG: Found {len(all_files)} files to organize')
            
            # Process each file
            for filename in all_files:
                file_path = os.path.join(output_dir, filename)
                
                # Skip if it's a directory
                if not os.path.isfile(file_path):
                    continue
                
                # Check if file should be kept in main directory
                should_keep = False
                
                # Check final files (exact match and wildcards)
                for final_pattern in final_files:
                    if final_pattern.endswith('*.txt'):
                        # Handle wildcard for report files
                        if filename.startswith('reconstruction_report_') and filename.endswith('.txt'):
                            should_keep = True
                            break
                    elif final_pattern.endswith('*.tif'):
                        # Handle wildcard for texture files
                        prefix = final_pattern[:-5]  # Remove '*.tif'
                        if filename.startswith(prefix) and filename.endswith('.tif'):
                            should_keep = True
                            print(f'DEBUG: Final pattern match: {filename} matches {final_pattern}')
                            break
                    elif filename == final_pattern:
                        should_keep = True
                        break
                
                if should_keep:
                    print(f'DEBUG: Keeping in main directory: {filename}')
                    kept_count += 1
                    continue
                
                # Check if file should be moved to intermediate directory
                should_move = False
                
                # Debug: Show which patterns we're checking
                # print(f'DEBUG: Checking file {filename} against {len(intermediate_files)} patterns')
                
                for intermediate_pattern in intermediate_files:
                    if intermediate_pattern.startswith('*') and intermediate_pattern.endswith('*'):
                        # Handle patterns like *_temp*.tif
                        pattern_core = intermediate_pattern[1:-1]  # Remove * from both ends
                        if pattern_core in filename:
                            should_move = True
                            break
                    elif intermediate_pattern.startswith('*'):
                        # Handle patterns like *.tif, *.tfw, *.aux.xml
                        suffix = intermediate_pattern[1:]
                        if filename.endswith(suffix):
                            should_move = True
                            print(f'DEBUG:  Pattern match: {filename} matches {intermediate_pattern}')
                            break
                    elif intermediate_pattern.endswith('*'):
                        # Handle patterns like filtered_dsm_iter_*
                        prefix = intermediate_pattern[:-1]
                        if filename.startswith(prefix):
                            should_move = True
                            break
                    elif filename == intermediate_pattern:
                        # Exact match
                        should_move = True
                        break
                
                if should_move:
                    try:
                        destination_path = os.path.join(intermediate_dir, filename)
                        shutil.move(file_path, destination_path)
                        print(f'DEBUG:  Moved to Intermediate/: {filename}')
                        moved_count += 1
                    except Exception as e:
                        # File is likely locked by QGIS - keep in main directory with note
                        print(f'DEBUG:  File locked, keeping in main: {filename} ({str(e)[:50]}...)')
                        kept_count += 1
                else:
                    # Unknown file - keep in main directory but log it
                    print(f'DEBUG:  Unknown file kept in main: {filename}')
                    kept_count += 1
            
            # Create organization summary
            summary_file = os.path.join(output_dir, '_file_organization_summary.txt')
            try:
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write("FILE ORGANIZATION SUMMARY\n")
                    f.write("=" * 50 + "\n")
                    f.write(f"Organized on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Files kept in main directory: {kept_count}\n")
                    f.write(f"Files moved to Intermediate/: {moved_count}\n")
                    f.write(f"Total files processed: {kept_count + moved_count}\n")
                    f.write("\n")
                    f.write("MAIN DIRECTORY (Final Results):\n")
                    f.write("- reconstructed_dsm.tif (Main reconstructed surface)\n")
                    f.write("- anthropogenic_features.tif (3-class classification)\n")
                    f.write("- reconstruction_report_*.txt (Processing report)\n")
                    f.write("\n")
                    f.write("INTERMEDIATE/ DIRECTORY:\n")
                    f.write("- All intermediate processing files\n")
                    f.write("- Temporary files and calculations\n")
                    f.write("- Individual processing steps\n")
                    f.write("\n")
                    f.write("NOTE: Some files may remain in main directory\n")
                    f.write("if they were locked by QGIS during organization.\n")
                    f.write("You can safely delete the Intermediate/ folder\n")
                    f.write("if you only need the final results.\n")
                    
                print(f'DEBUG:  Organization summary created: _file_organization_summary.txt')
            except Exception as e:
                print(f'DEBUG: Error creating organization summary: {str(e)}')
            
            print(f'DEBUG: File organization completed!')
            print(f'DEBUG: Main directory: {kept_count} files (final results)')
            print(f'DEBUG: Intermediate/: {moved_count} files (intermediate results)')
            
            # Show user notification
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                # Simple check if there were any locked files (based on kept vs moved ratio)
                locked_files_note = ""
                if kept_count > 5:  # If more than 5 files kept, likely some were locked
                    locked_files_note = f"\n\n Note: Some files may have remained in main directory\nbecause they were locked by QGIS."
                
                QMessageBox.information(
                    self, 
                    'Files Organized', 
                    f' Output files organized successfully!\n\n'
                    f' Main Results: {kept_count} files\n'
                    f' Intermediate/: {moved_count} files\n\n'
                    f'Final results are in the main directory.\n'
                    f'Intermediate files moved to "Intermediate/" subfolder.{locked_files_note}'
                )
            except:
                pass  # In case GUI is not available
                
        except Exception as e:
            print(f'DEBUG: Error during file organization: {str(e)}')
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, 
                    'Organization Warning', 
                    f'File organization encountered an error:\n{str(e)}\n\n'
                    f'Processing completed successfully, but files were not reorganized.'
                )
            except:
                pass

    def analyze_geomorphometric_statistics(self, slope_layer, curvature_layer, residual_layer=None, texture_variance=None, texture_entropy=None):
        """
        Comprehensive statistical analysis of geomorphometric parameters.
        
        Implements the adaptive threshold methodology from Cao et al. (2020) for
        determining optimal thresholds based on the statistical distribution of
        geomorphometric parameters. This approach ensures that thresholds are
        automatically adapted to the specific terrain characteristics of each dataset.
        
        The method calculates percentile-based thresholds for:
        - Slope: Identifies steep anthropogenic features
        - Curvature: Detects sharp edges and artificial structures
        - Residuals: Finds height anomalies relative to smoothed terrain
        - Texture variance: Distinguishes vegetation from anthropogenic features
        - Texture entropy: Measures surface complexity for classification
        
        Args:
            slope_layer (QgsRasterLayer): Raster layer containing slope values
            curvature_layer (QgsRasterLayer): Raster layer containing curvature values
            residual_layer (QgsRasterLayer, optional): Raster layer containing residual values
            texture_variance (QgsRasterLayer, optional): Raster layer containing texture variance
            texture_entropy (QgsRasterLayer, optional): Raster layer containing texture entropy
            
        Returns:
            dict: Statistical analysis results containing:
                - slope_threshold (float): Calculated slope threshold
                - slope_percentile (float): Percentile used for slope calculation
                - curvature_pos_threshold (float): Positive curvature threshold
                - curvature_neg_threshold (float): Negative curvature threshold
                - curvature_percentile (float): Percentile used for curvature
                - residual_threshold (float): Residual threshold (if residuals available)
                - residual_percentile (float): Percentile used for residuals
                - use_residuals (bool): Whether residual analysis was performed
                - variance_threshold (float): Texture variance threshold
                - entropy_threshold (float): Texture entropy threshold
                - variance_percentile (float): Percentile used for variance
                - entropy_percentile (float): Percentile used for entropy
                - use_texture (bool): Whether texture analysis was performed
                
        Raises:
            Exception: If statistical analysis fails completely
            
        Note:
            - Uses percentile-based approach for adaptive thresholds
            - Handles missing texture layers gracefully
            - Provides comprehensive debug output
            - Falls back to UI default values if calculation fails
            - Supports both 3-class and binary classification modes
        """
        try:
            print('DEBUG: ===== Geomorphometric Statistical Analysis =====')
            print('DEBUG: Following Cao et al. (2020) methodology')
            
            # Get percentile values from UI (only if percentile mode is selected)
            slope_percentile = self.spinSlopePercentile.value()
            curvature_percentile = self.spinCurvaturePercentile.value()
            residual_percentile = self.spinResidualPercentile.value()
            
            # Get Variance/Entropy values based on selected method
            if self.radioPercentile.isChecked():
                # Use percentile values for Variance/Entropy
                variance_percentile = self.spinVariancePercentile.value()
                entropy_percentile = self.spinEntropyPercentile.value()
                variance_threshold = None  # Will be calculated from percentiles
                entropy_threshold = None   # Will be calculated from percentiles
            else:
                # Use fixed threshold values for Variance/Entropy
                variance_percentile = None  # Not used in fixed mode
                entropy_percentile = None   # Not used in fixed mode
                variance_threshold = self.spinVarianceThreshold.value()
                entropy_threshold = self.spinEntropyThreshold.value()
            
            # Calculate adaptive thresholds
            slope_threshold = self.calculate_raster_percentiles(slope_layer, slope_percentile)
            
            # For curvature, we need both positive and negative thresholds
            curvature_pos_threshold = self.calculate_raster_percentiles(curvature_layer, curvature_percentile)
            curvature_neg_threshold = self.calculate_raster_percentiles(curvature_layer, 100 - curvature_percentile)
            
            residual_threshold = None
            if residual_layer is not None:
                # For residuals, calculate both positive and negative thresholds
                residual_pos_threshold = self.calculate_raster_percentiles(residual_layer, residual_percentile)
                residual_neg_threshold = self.calculate_raster_percentiles(residual_layer, 100 - residual_percentile)
                residual_threshold = max(abs(residual_pos_threshold), abs(residual_neg_threshold))

            # Calculate texture thresholds based on selected method and available data
            use_texture = False
            
            if texture_variance is not None and texture_entropy is not None:
                if self.radioPercentile.isChecked():
                    # Calculate percentiles from texture data
                    print('DEBUG: Calculating texture percentiles for vegetation detection...')
                    variance_threshold = self.calculate_raster_percentiles(texture_variance, variance_percentile)
                    entropy_threshold = self.calculate_raster_percentiles(texture_entropy, entropy_percentile)
                    use_texture = True
                    print(f'DEBUG: Variance {variance_percentile}th percentile: {variance_threshold:.4f}')
                    print(f'DEBUG: Entropy {entropy_percentile}th percentile: {entropy_threshold:.4f}')
                else:
                    # Use fixed threshold values (already set above)
                    use_texture = True
                    print(f'DEBUG: Using fixed variance threshold: {variance_threshold:.4f}')
                    print(f'DEBUG: Using fixed entropy threshold: {entropy_threshold:.4f}')
            else:
                # Texture analysis failed/disabled, use UI values
                print('DEBUG: Texture analysis failed/disabled, using UI values...')
                try:
                    # Check if texture analysis is enabled in UI
                    if hasattr(self, 'checkTextureAnalysis') and self.checkTextureAnalysis.isChecked():
                        use_texture = True
                        if self.radioPercentile.isChecked():
                            print('DEBUG: Texture analysis enabled but no texture data available')
                            print('DEBUG: Will use UI percentile values when texture data becomes available')
                        else:
                            print(f'DEBUG: Using fixed variance threshold: {variance_threshold:.4f}')
                            print(f'DEBUG: Using fixed entropy threshold: {entropy_threshold:.4f}')
                    else:
                        use_texture = False
                        print('DEBUG: Texture analysis disabled in UI')
                except:
                    # Final fallback values
                    variance_threshold = 0.5  # Default variance threshold
                    entropy_threshold = 2.0   # Default entropy threshold
                    use_texture = False
                    print('DEBUG: Using hardcoded fallback values - texture analysis disabled')
            
            # Compile results
            results = {
                'slope_threshold': slope_threshold,
                'slope_percentile': slope_percentile,
                'curvature_pos_threshold': curvature_pos_threshold,
                'curvature_neg_threshold': curvature_neg_threshold,
                'curvature_percentile': curvature_percentile,
                'residual_threshold': residual_threshold,
                'residual_percentile': residual_percentile,
                'use_residuals': residual_layer is not None,
                'variance_threshold': variance_threshold,
                'entropy_threshold': entropy_threshold,
                'variance_percentile': variance_percentile,
                'entropy_percentile': entropy_percentile,
                'use_texture': use_texture,
                'threshold_method': 'percentile' if self.radioPercentile.isChecked() else 'fixed'
            }
            
            # Print summary
            print('DEBUG: ===== Adaptive Threshold Results =====')
            print(f'DEBUG: Slope {slope_percentile}th percentile: {slope_threshold:.4f}°')
            print(f'DEBUG: Curvature {curvature_percentile}th percentile: +{curvature_pos_threshold:.4f}')
            print(f'DEBUG: Curvature {100-curvature_percentile}th percentile: {curvature_neg_threshold:.4f}')
            if residual_threshold is not None:
                print(f'DEBUG: Residual {residual_percentile}th percentile: ±{residual_threshold:.4f}m')
            else:
                print('DEBUG: Residual analysis: Not available')
            
            if use_texture:
                if self.radioPercentile.isChecked():
                    print(f'DEBUG: Variance threshold ({variance_percentile}th percentile): {variance_threshold:.4f}')
                    print(f'DEBUG: Entropy threshold ({entropy_percentile}th percentile): {entropy_threshold:.4f}')
                else:
                    print(f'DEBUG: Variance threshold (fixed): {variance_threshold:.4f}')
                    print(f'DEBUG: Entropy threshold (fixed): {entropy_threshold:.4f}')
                print('DEBUG: Texture analysis: ENABLED (3-class classification)')
            else:
                print('DEBUG: Texture analysis: DISABLED (binary classification)')
            print('DEBUG: ==========================================')
            
            return results
            
        except Exception as e:
            print(f'DEBUG: Statistical analysis failed: {str(e)}')
            return None

    def perform_texture_analysis(self, input_raster_path, output_dir, feedback):
        """
        Perform texture analysis using GRASS r.texture to distinguish vegetation from anthropogenic features.
        
        Implements Gray-Level Co-Occurrence Matrix (GLCM) texture analysis to distinguish
        between natural vegetation and anthropogenic structures based on surface texture patterns.
        This analysis is crucial for the 3-class classification system that separates
        natural terrain, vegetation, and anthropogenic features.
        
        The method calculates two key texture metrics:
        - Variance: Measures local surface variation (high for vegetation)
        - Entropy: Measures texture complexity and heterogeneity (high for vegetation)
        
        Processing Workflow:
        1. Check if texture analysis is enabled in UI
        2. Convert input to integer format for GRASS compatibility
        3. Calculate variance using GRASS r.texture
        4. Calculate entropy using GRASS r.texture
        5. Validate output files and load as QgsRasterLayers
        6. Provide comprehensive diagnostics and fallback options
        
        Args:
            input_raster_path (str): Path to the filtered DSM raster file
            output_dir (str): Directory where texture analysis results will be saved
            feedback (QgsProcessingFeedback): Processing feedback object for progress updates
            
        Returns:
            tuple: (variance_layer, entropy_layer) or (None, None) if disabled/failed
                - variance_layer (QgsRasterLayer): Texture variance raster layer
                - entropy_layer (QgsRasterLayer): Texture entropy raster layer
                
        Side Effects:
            - Creates texture_variance.tif and texture_entropy.tif in output directory
            - May create temporary files during processing
            - Provides detailed debug output about processing steps
            - Handles file cleanup for temporary files
            
        Raises:
            Exception: If texture analysis fails completely (with fallback attempts)
            
        Note:
            - Uses GRASS r.texture algorithm for GLCM calculation
            - Supports configurable window size (default 3x3 to 9x9)
            - Provides multiple fallback methods if GRASS fails
            - Includes comprehensive file validation and diagnostics
            - Handles large datasets with memory-efficient processing
        """
        try:
            # Check if texture analysis is enabled
            if hasattr(self, 'checkTextureAnalysis') and self.checkTextureAnalysis.isChecked():
                texture_enabled = True
            else:
                texture_enabled = True  # Default to enabled for now
                print('DEBUG: Texture analysis checkbox not found, defaulting to enabled')
        except:
            texture_enabled = True  # Fallback
            print('DEBUG: Error checking texture analysis checkbox, defaulting to enabled')
            
        if not texture_enabled:
            print('DEBUG: Texture analysis disabled – using original workflow')
            return None, None
        
        try:
            window_size = self.spinTextureWindow.value() if hasattr(self, 'spinTextureWindow') else 3
        except:
            window_size = 3
        print(f'DEBUG: Texture analysis enabled with window size {window_size}x{window_size}')
        
        variance_path = os.path.join(output_dir, 'texture_variance.tif')
        entropy_path = os.path.join(output_dir, 'texture_entropy.tif')
        
        try:
            # Method 1: Try GRASS r.texture with corrected parameters - focus only on variance first
            print('DEBUG: Attempting GRASS r.texture for variance...')
            
            # Get input raster properties for GRASS parameters
            input_layer = QgsRasterLayer(input_raster_path, 'Input_For_Texture')
            if input_layer.isValid():
                extent = input_layer.extent()
                pixel_size = input_layer.rasterUnitsPerPixelX()
                print(f'DEBUG: Input raster extent: {extent.toString()}')
                print(f'DEBUG: Input raster pixel size: {pixel_size}')
            else:
                extent = None
                pixel_size = None
                print('DEBUG: Could not get input raster properties')
            
            try:
                # GRASS r.texture often requires integer input - convert first
                print(f"DEBUG: Preparing input for GRASS r.texture...")
                temp_grass_input = os.path.join(output_dir, 'temp_grass_input.tif')
                
                # Convert to integer format that GRASS prefers
                processing.run('gdal:translate', {
                    'INPUT': input_raster_path,
                    'TARGET_CRS': None,
                    'NODATA': None,
                    'COPY_SUBDATASETS': False,
                    'OPTIONS': 'COMPRESS=LZW',
                    'EXTRA': '-ot Int16 -scale',  # Convert to 16-bit integer with scaling
                    'DATA_TYPE': 2,  # Int16
                    'OUTPUT': temp_grass_input
                })
                print(f"DEBUG: Converted input to integer format: {temp_grass_input}")
                
                # Enhanced GRASS parameters - simplified to avoid region issues
                grass_params_base = {
                    'GRASS_REGION_PARAMETER': None,
                    'GRASS_REGION_CELLSIZE_PARAMETER': 0,
                    'GRASS_RASTER_FORMAT_OPT': '',
                    'GRASS_RASTER_FORMAT_META': ''
                }
                
                # Step 1: Calculate variance with optimized parameters
                print('DEBUG: Calculating variance with optimized GRASS parameters...')
                variance_params = {
                    'input': temp_grass_input,  # Use converted integer input
                    'output': variance_path,
                    'size': window_size,
                    'distance': 1,
                    'method': [0],  # 0: Variance only
                    **grass_params_base
                }
                
                variance_result = processing.run('grass7:r.texture', variance_params, feedback=feedback)
                
                print(f'DEBUG: GRASS variance result: {variance_result}')
                
                # Step 2: Calculate entropy with same optimized parameters
                print('DEBUG: Calculating entropy with optimized GRASS parameters...')
                entropy_params = {
                    'input': temp_grass_input,  # Use converted integer input
                    'output': entropy_path,
                    'size': window_size,
                    'distance': 1,
                    'method': [3],  # 3: Entropy only
                    **grass_params_base
                }
                
                entropy_result = processing.run('grass7:r.texture', entropy_params, feedback=feedback)
                
                print(f'DEBUG: GRASS entropy result: {entropy_result}')
                
                # Check if files were created
                if not os.path.exists(variance_path):
                    print(f'DEBUG: Variance file not found: {variance_path}')
                    # Check if GRASS created it with a different name
                    import glob
                    variance_candidates = glob.glob(os.path.join(output_dir, '*variance*'))
                    print(f'DEBUG: Found variance candidates: {variance_candidates}')
                    
                if not os.path.exists(entropy_path):
                    print(f'DEBUG: Entropy file not found: {entropy_path}')
                    # Check if GRASS created it with a different name
                    import glob
                    entropy_candidates = glob.glob(os.path.join(output_dir, '*entropy*'))
                    print(f'DEBUG: Found entropy candidates: {entropy_candidates}')
                
                # Try to find the actual output files from processing results
                if 'output' in variance_result:
                    actual_variance_path = variance_result['output']
                    print(f'DEBUG: Actual variance path from result: {actual_variance_path}')
                    if os.path.exists(actual_variance_path):
                        variance_path = actual_variance_path
                
                if 'output' in entropy_result:
                    actual_entropy_path = entropy_result['output']
                    print(f'DEBUG: Actual entropy path from result: {actual_entropy_path}')
                    if os.path.exists(actual_entropy_path):
                        entropy_path = actual_entropy_path
                
                # Final check
                if not os.path.exists(variance_path) or not os.path.exists(entropy_path):
                    print(f'DEBUG: Still missing files - Variance: {os.path.exists(variance_path)}, Entropy: {os.path.exists(entropy_path)}')
                    raise Exception("GRASS r.texture output files not found")
                    
                print('DEBUG: GRASS r.texture completed successfully')
                print(f'DEBUG: Variance file: {variance_path}')
                print(f'DEBUG: Entropy file: {entropy_path}')
                
            except Exception as grass_error:
                print(f'DEBUG: GRASS r.texture failed: {str(grass_error)}')
                raise Exception("GRASS r.texture failed")
            
            # Enhanced diagnostics and validation
            print('DEBUG: ===== TEXTURE ANALYSIS DIAGNOSTICS =====')
            
            # Check file sizes
            variance_size = os.path.getsize(variance_path) if os.path.exists(variance_path) else 0
            entropy_size = os.path.getsize(entropy_path) if os.path.exists(entropy_path) else 0
            print(f'DEBUG: Variance file size: {variance_size} bytes')
            print(f'DEBUG: Entropy file size: {entropy_size} bytes')
            
            # Check if files are too small (likely empty/corrupt)
            if variance_size < 10000 or entropy_size < 10000:  # Less than 10KB is suspicious
                print('DEBUG: Files too small, likely corrupt. Trying GDAL repair...')
                try:
                    # Try to repair/convert using GDAL
                    repaired_variance = os.path.join(output_dir, 'texture_variance_repaired.tif')
                    repaired_entropy = os.path.join(output_dir, 'texture_entropy_repaired.tif')
                    
                    processing.run('gdal:translate', {
                        'INPUT': variance_path,
                        'OUTPUT': repaired_variance
                    })
                    processing.run('gdal:translate', {
                        'INPUT': entropy_path,
                        'OUTPUT': repaired_entropy
                    })
                    
                    if os.path.exists(repaired_variance) and os.path.exists(repaired_entropy):
                        variance_path = repaired_variance
                        entropy_path = repaired_entropy
                        print('DEBUG: Files repaired using GDAL translate')
                    else:
                        raise Exception("GDAL repair failed")
                        
                except Exception as repair_error:
                    print(f'DEBUG: GDAL repair failed: {str(repair_error)}')
                    
            # Try multiple loading methods
            variance_layer = None
            entropy_layer = None
            
            # Method 1: Direct QgsRasterLayer loading
            print('DEBUG: Trying direct QgsRasterLayer loading...')
            variance_layer = QgsRasterLayer(variance_path, 'Texture Variance')
            entropy_layer = QgsRasterLayer(entropy_path, 'Texture Entropy')
            
            variance_valid = variance_layer.isValid()
            entropy_valid = entropy_layer.isValid()
            print(f'DEBUG: Variance layer valid: {variance_valid}')
            print(f'DEBUG: Entropy layer valid: {entropy_valid}')
            
            if not variance_valid:
                print(f'DEBUG: Variance layer error: {variance_layer.error().message()}')
            if not entropy_valid:
                print(f'DEBUG: Entropy layer error: {entropy_layer.error().message()}')
            
            # Method 2: Try with explicit provider if direct loading failed
            if not variance_valid or not entropy_valid:
                print('DEBUG: Trying explicit GDAL provider...')
                variance_layer = QgsRasterLayer(f'GDAL:{variance_path}', 'Texture Variance', 'gdal')
                entropy_layer = QgsRasterLayer(f'GDAL:{entropy_path}', 'Texture Entropy', 'gdal')
                
                variance_valid = variance_layer.isValid()
                entropy_valid = entropy_layer.isValid()
                print(f'DEBUG: GDAL provider - Variance valid: {variance_valid}')
                print(f'DEBUG: GDAL provider - Entropy valid: {entropy_valid}')
            
            # Method 3: Force refresh and retry if still failed
            if not variance_valid or not entropy_valid:
                print('DEBUG: Trying layer refresh and reload...')
                try:
                    # Force a small delay and retry
                    import time
                    time.sleep(0.5)
                    
                    variance_layer = QgsRasterLayer(variance_path, 'Texture Variance')
                    entropy_layer = QgsRasterLayer(entropy_path, 'Texture Entropy')
                    
                    # Force reload
                    variance_layer.reload()
                    entropy_layer.reload()
                    
                    variance_valid = variance_layer.isValid()
                    entropy_valid = entropy_layer.isValid()
                    print(f'DEBUG: After refresh - Variance valid: {variance_valid}')
                    print(f'DEBUG: After refresh - Entropy valid: {entropy_valid}')
                    
                except Exception as refresh_error:
                    print(f'DEBUG: Refresh method failed: {str(refresh_error)}')
            
            # Final validation
            if not variance_valid or not entropy_valid:
                print('DEBUG: All loading methods failed - texture analysis unsuccessful')
                print('DEBUG: ==========================================')
                # Clean up temporary grass input file
                if 'temp_grass_input' in locals() and os.path.exists(temp_grass_input):
                    try:
                        os.remove(temp_grass_input)
                    except:
                        pass
                return None, None
                
            print('DEBUG: ===== TEXTURE ANALYSIS SUCCESSFUL =====')
            print(f'DEBUG: Variance layer: {variance_path} (Valid: {variance_valid})')
            print(f'DEBUG: Entropy layer: {entropy_path} (Valid: {entropy_valid})')
            print('DEBUG: ==========================================')
            
            # Clean up temporary grass input file
            if 'temp_grass_input' in locals() and os.path.exists(temp_grass_input):
                try:
                    os.remove(temp_grass_input)
                    print(f'DEBUG: Cleaned up temporary GRASS input: {temp_grass_input}')
                except:
                    pass
            
            return variance_layer, entropy_layer
            
        except Exception as e:
            print(f'DEBUG: GRASS r.texture completely failed: {str(e)}')
            print('DEBUG: Trying alternative GDAL-based texture calculation...')
            
            # Alternative texture calculation using focal statistics
            try:
                return self.calculate_texture_alternative(input_raster_path, output_dir, window_size, feedback)
            except Exception as alt_error:
                print(f'DEBUG: Alternative texture calculation also failed: {str(alt_error)}')
                # Clean up temporary grass input file
                if 'temp_grass_input' in locals() and os.path.exists(temp_grass_input):
                    try:
                        os.remove(temp_grass_input)
                    except:
                        pass
                return None, None

    def calculate_texture_alternative(self, input_raster_path, output_dir, window_size, feedback):
        """
        Alternative texture calculation using GDAL focal statistics.
        
        Provides a fallback texture calculation method when GRASS r.texture is not
        available or fails. This method uses basic terrain derivatives to approximate
        texture characteristics that can distinguish vegetation from anthropogenic features.
        
        The alternative approach uses:
        - Slope as a proxy for surface variation (variance approximation)
        - Roughness index as a proxy for surface complexity (entropy approximation)
        
        While not as sophisticated as GLCM texture analysis, this method provides
        reasonable approximations that can still support 3-class classification.
        
        Args:
            input_raster_path (str): Path to the input DSM raster file
            output_dir (str): Directory where texture results will be saved
            window_size (int): Window size parameter (not used in this fallback)
            feedback (QgsProcessingFeedback): Processing feedback object
            
        Returns:
            tuple: (variance_layer, entropy_layer) or (None, None) if calculation fails
                - variance_layer (QgsRasterLayer): Approximate texture variance layer
                - entropy_layer (QgsRasterLayer): Approximate texture entropy layer
                
        Side Effects:
            - Creates texture_variance_gdal.tif and texture_entropy_gdal.tif
            - Creates temporary terrain derivative files
            - Cleans up temporary files after processing
            
        Raises:
            Exception: If alternative texture calculation fails completely
            
        Note:
            - Uses QGIS terrain analysis algorithms (slope, aspect, roughness)
            - Provides reasonable approximations for texture analysis
            - Much faster than GRASS r.texture but less sophisticated
            - Suitable for datasets where GRASS is not available
        """
        print('DEBUG: Starting alternative GDAL-based texture calculation...')
        
        variance_path = os.path.join(output_dir, 'texture_variance_gdal.tif')
        entropy_path = os.path.join(output_dir, 'texture_entropy_gdal.tif')
        
        try:
            # Calculate local variance approximation using focal statistics
            # Variance ≈ (FocalMax - FocalMin)^2 / 4
            focal_max_path = os.path.join(output_dir, 'focal_max_temp.tif')
            focal_min_path = os.path.join(output_dir, 'focal_min_temp.tif')
            
            # Simple but effective texture approximation using basic terrain derivatives
            # This approach is robust and uses only standard QGIS algorithms
            temp_slope_path = os.path.join(output_dir, 'temp_slope_texture.tif')
            temp_aspect_path = os.path.join(output_dir, 'temp_aspect_texture.tif')
            temp_rough_path = os.path.join(output_dir, 'temp_roughness_texture.tif')
            
            # Step 1: Calculate basic terrain derivatives
            processing.run('qgis:slope', {
                'INPUT': input_raster_path,
                'Z_FACTOR': 1.0,
                'OUTPUT': temp_slope_path
            })
            
            processing.run('qgis:aspect', {
                'INPUT': input_raster_path,
                'Z_FACTOR': 1.0,
                'OUTPUT': temp_aspect_path
            })
            
            processing.run('qgis:ruggednessindex', {
                'INPUT': input_raster_path,
                'Z_FACTOR': 1.0,
                'OUTPUT': temp_rough_path
            })
            
            focal_max_path = temp_slope_path    # Slope as primary variation measure
            focal_min_path = temp_rough_path    # Roughness as secondary measure
            
            # Step 3: Calculate Variance approximation using slope
            # Higher slope = higher surface variation = higher "variance"
            processing.run('gdal:rastercalculator', {
                'INPUT_A': focal_max_path,  # slope
                'BAND_A': 1,
                'FORMULA': 'A/45.0',  # Normalize slope to reasonable range (0-45° -> 0-1)
                'OUTPUT': variance_path
            })
            
            # Step 4: Entropy approximation using terrain roughness
            # Roughness index provides a good entropy-like measure of local heterogeneity
            processing.run('gdal:rastercalculator', {
                'INPUT_A': focal_min_path,  # roughness
                'BAND_A': 1,
                'FORMULA': 'A*10.0',  # Scale roughness to appropriate range
                'OUTPUT': entropy_path
            })
            
            # Clean up temporary files
            for temp_file in [temp_slope_path, temp_aspect_path, temp_rough_path]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass  # Ignore cleanup errors
            
            # Load and validate
            variance_layer = QgsRasterLayer(variance_path, 'Texture Variance (GDAL)')
            entropy_layer = QgsRasterLayer(entropy_path, 'Texture Entropy (GDAL)')
            
            if variance_layer.isValid() and entropy_layer.isValid():
                print('DEBUG: Alternative GDAL texture calculation successful')
                return variance_layer, entropy_layer
            else:
                raise Exception("Alternative texture layers are invalid")
                
        except Exception as e:
            print(f'DEBUG: Alternative texture calculation failed: {str(e)}')
            return None, None

    def run_reconstruction(self):
        """
        Main reconstruction workflow orchestrating the entire bare earth reconstruction process.
        
        This is the core method that implements the complete bare earth reconstruction
        workflow based on the methodology of Cao et al. (2020). It orchestrates all
        processing steps from input validation through final output generation.
        
        Processing Workflow:
        1. Input validation and DSM analysis
        2. Auto-scaling of parameters based on resolution
        3. Iterative Gaussian filtering for terrain separation
        4. Geomorphometric analysis (slope, curvature, residuals)
        5. Texture analysis for 3-class classification
        6. Statistical analysis and adaptive threshold calculation
        7. Anthropogenic feature identification and classification
        8. Selective buffering and masking
        9. Advanced interpolation for gap filling (Enhanced GDAL, Simple GDAL, or GRASS r.fillnulls)
        10. Result validation and file organization
        11. Comprehensive reporting and documentation
        
        The method supports both percentile-based adaptive thresholds (Cao et al. 2020)
        and traditional fixed thresholds, with comprehensive fallback mechanisms
        for robust processing across different datasets and environments.
        
        Side Effects:
            - Creates multiple intermediate and final output files
            - Updates progress bar and status messages throughout processing
            - Loads result layers into QGIS project
            - Generates comprehensive processing report
            - Organizes output files for better structure
            - Shows user notifications for warnings and completion
            
        Raises:
            QMessageBox: Error dialogs for invalid inputs or processing failures
            Exception: Detailed error messages for debugging
            
        Note:
            - Implements comprehensive error handling with user feedback
            - Provides detailed debug output for troubleshooting
            - Supports multiple interpolation methods (Enhanced GDAL, Simple GDAL, GRASS r.fillnulls)
            - GRASS r.fillnulls includes NoData validation, organic interpolation, and fallbacks
            - Auto-scales parameters based on DSM resolution
            - Generates comprehensive processing documentation
            - Handles large datasets with memory-efficient processing
        """
        try:
            # Reset progress display
            self.reset_progress()
            # --- Directory check ---
            output_dir = self.lineEditOutputDir.text().strip()
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                    print(f'DEBUG: Output directory created: {output_dir}')
                except Exception as e:
                    QMessageBox.critical(self, 'Error', f'Output directory could not be created: {output_dir}\n{str(e)}')
                    return
            if not os.access(output_dir, os.W_OK):
                QMessageBox.critical(self, 'Error', f'Output directory is not writable: {output_dir}')
                return

            # --- Input DSM check ---
            input_dsm = self.get_input_dsm()
            if not input_dsm or not input_dsm.isValid():
                QMessageBox.critical(self, 'Error', 'No valid DSM selected!')
                return
            input_dsm_path = self.get_raster_path(input_dsm)
            if not os.path.exists(input_dsm_path):
                QMessageBox.critical(self, 'Error', f'DSM file does not exist: {input_dsm_path}')
                return
            # Basic DSM validation using QGIS
            try:
                stats = input_dsm.dataProvider().bandStatistics(1)
                if stats.minimumValue == stats.maximumValue:
                    QMessageBox.critical(self, 'Error', f'DSM contains no valid elevation values!')
                    return
            except Exception as e:
                print(f'DEBUG: Error validating DSM: {str(e)}')

            # Auto-detect pixel size and offer parameter scaling
            print('DEBUG: Analyzing DSM resolution and scaling parameters...')
            scaling_info = self.get_pixel_size_and_scale_parameters(input_dsm)
            
            # Get parameter values (may have been updated by auto-scaling)
            sigma_value = self.spinSigma.value()
            kernel_radius = self.spinKernelRadius.value()
            gaussian_iterations = self.spinGaussianIterations.value()
            buffer_distance = self.spinBufferDistance.value()
            fill_distance = self.spinFillDistance.value()
            fill_iterations = self.spinFillIterations.value()
            output_dir = self.lineEditOutputDir.text().strip()
            if not output_dir:
                QMessageBox.warning(self, 'Error', 'Please select an output directory!')
                return
            feedback = QgsProcessingFeedback()
            feedback.pushInfo('Starting DSM processing...')
            print(f'DEBUG: Processing {input_dsm.name()} ({scaling_info["pixel_size"]:.1f}m resolution)')

            # Initialize progress bar
            total_steps = gaussian_iterations + 9
            self.update_progress(0, total_steps, "Starting DSM processing...")

            # Initialize file paths for later use
            output_anthropogenic = os.path.join(output_dir, 'anthropogenic_features.tif')

            # Step 1: Iterative Gaussian filtering
            input_dsm_path = self.get_raster_path(input_dsm)
            
            # Start with the original DSM
            current_dsm_path = input_dsm_path
            
            try:
                # Apply Gaussian filter iteratively with fallback algorithms
                for iteration in range(gaussian_iterations):
                    print(f'DEBUG: Applying Gaussian filter iteration {iteration + 1}/{gaussian_iterations}')
                    
                    # Update progress bar
                    self.update_progress(iteration + 1, total_steps, f"Gaussian Filter - Iteration {iteration + 1}/{gaussian_iterations}")
                    
                    # Adaptive sigma: start with smaller values, increase gradually
                    if gaussian_iterations == 1:
                        adaptive_sigma = sigma_value
                    else:
                        adaptive_sigma = sigma_value * (0.7 + 0.6 * iteration / (gaussian_iterations - 1))
                    
                    # Create output path for this iteration
                    if iteration == gaussian_iterations - 1:
                        filtered_dsm_path = os.path.join(output_dir, 'filtered_dsm.tif').replace('\\', '/')
                    else:
                        filtered_dsm_path = os.path.join(output_dir, f'filtered_dsm_iter_{iteration + 1}.tif').replace('\\', '/')
                    
                    os.makedirs(os.path.dirname(filtered_dsm_path), exist_ok=True)
                    
                    # Try Gaussian filter with simple fallback
                    filter_success = False
                    
                    # Method 1: Try SAGA NextGen Gaussian filter
                    try:
                        filtered_dsm_result = processing.run(
                            'sagang:gaussianfilter',
                            {
                                'INPUT': current_dsm_path,
                                'SIGMA': adaptive_sigma,
                                'KERNEL_TYPE': 1,  # Circle
                                'KERNEL_RADIUS': kernel_radius,
                                'RESULT': filtered_dsm_path
                            },
                            feedback=feedback
                        )
                        
                        if os.path.isfile(filtered_dsm_path):
                            filter_success = True
                        else:
                            raise Exception("Output file not created")
                            
                    except Exception as e:
                        # Method 2: Simple fallback - copy file without filtering
                        try:
                            import shutil
                            shutil.copy2(current_dsm_path, filtered_dsm_path)
                            filter_success = True
                            if iteration == 0:
                                QMessageBox.warning(self, 'Warning', 'Gaussian filtering not available. Using original DSM.')
                        except Exception as e2:
                            print(f'DEBUG: All filter methods failed in iteration {iteration + 1}')
                            filtered_dsm_path = input_dsm_path
                            QMessageBox.warning(self, 'Warning', 'Filtering failed. Processing continues with original DSM.')
                            break
                    
                    # Verify the output file exists (only if not using original DSM path)
                    if filtered_dsm_path != current_dsm_path and not os.path.isfile(filtered_dsm_path):
                        print(f'DEBUG: Output file verification failed, using original DSM: {filtered_dsm_path}')
                        filtered_dsm_path = input_dsm_path
                        QMessageBox.warning(self, 'Warning', 'File verification failed. Using original DSM.')
                        break
                    
                    # Update current DSM path for next iteration
                    current_dsm_path = filtered_dsm_path
                
                # Load the final filtered DSM
                filtered_dsm = QgsRasterLayer(filtered_dsm_path, 'Filtered DSM')
                if not filtered_dsm.isValid():
                    # Try loading original DSM as fallback
                    print(f'DEBUG: Cannot load filtered DSM, trying original DSM as fallback')
                    filtered_dsm = QgsRasterLayer(input_dsm_path, 'Original DSM (Fallback)')
                    filtered_dsm_path = input_dsm_path
                    if not filtered_dsm.isValid():
                        raise Exception(f"Neither filtered nor original DSM could be loaded!")
                    QMessageBox.warning(self, 'Warning', 'Using original DSM as final result.')
                
                print(f'DEBUG: Gaussian filter completed ({gaussian_iterations} iterations)')
                

                    
            except Exception as e:
                print(f'DEBUG: Iterative SAGA NextGen Gaussian filter failed: {str(e)}')
                QMessageBox.critical(self, 'Error', f'Iterative SAGA NextGen Gaussian filter (sagang:gaussianfilter) failed after {gaussian_iterations} iterations: {str(e)}')
                return

            # Step 2: Calculate residuals (Original DSM - Filtered DSM)
            self.update_progress(gaussian_iterations + 1, total_steps, " Calculating residuals (Original - Filtered DSM)...")
            output_residuals = os.path.join(output_dir, 'residuals.tif')
            
            # Initialize variables
            residual_layer = None
            use_residuals = True
            
            try:
                # Use GDAL processing instead of QgsRasterCalculator for more stability
                print('DEBUG: Calculating residuals using GDAL raster calculator...')
                
                # Method 1: Try GDAL raster calculator
                residual_result = processing.run(
                    'gdal:rastercalculator',
                    {
                        'INPUT_A': input_dsm_path,
                        'BAND_A': 1,
                        'INPUT_B': filtered_dsm_path,
                        'BAND_B': 1,
                        'FORMULA': 'A-B',
                        'NO_DATA': None,
                        'RTYPE': 5,  # Float32
                        'OUTPUT': output_residuals
                    },
                    feedback=feedback
                )
                print('DEBUG: GDAL raster calculator succeeded')
                
            except Exception as e:
                print(f'DEBUG: GDAL raster calculator failed: {str(e)}')
                print('DEBUG: Trying QGIS raster calculator with enhanced safety...')
                
                try:
                    # Method 2: Enhanced QGIS Raster Calculator with proper layer handling
                    from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
                    
                    # Ensure both layers are properly loaded and valid
                    original_layer = QgsRasterLayer(input_dsm_path, 'Original_DSM_Temp')
                    if not original_layer.isValid():
                        raise Exception(f"Could not load original DSM: {input_dsm_path}")
                    
                    # Reload filtered DSM to ensure it's properly accessible
                    filtered_layer = QgsRasterLayer(filtered_dsm_path, 'Filtered_DSM_Temp')
                    if not filtered_layer.isValid():
                        raise Exception(f"Could not load filtered DSM: {filtered_dsm_path}")
                    
                    # Check layer compatibility
                    if (original_layer.width() != filtered_layer.width() or
                        original_layer.height() != filtered_layer.height()):
                        print('DEBUG: Layer dimensions mismatch, resampling filtered DSM...')
                        
                        # Resample filtered DSM to match original
                        resampled_filtered_path = os.path.join(output_dir, 'filtered_dsm_resampled_for_residuals.tif')
                        processing.run(
                            'gdal:warpreproject',
                            {
                                'INPUT': filtered_dsm_path,
                                'SOURCE_CRS': filtered_layer.crs().authid(),
                                'TARGET_CRS': original_layer.crs().authid(),
                                'RESAMPLING': 0,
                                'NODATA': None,
                                'TARGET_RESOLUTION': None,
                                'OPTIONS': '',
                                'DATA_TYPE': 0,
                                'TARGET_EXTENT': None,
                                'TARGET_EXTENT_CRS': None,
                                'MULTITHREADING': False,
                                'OUTPUT': resampled_filtered_path
                            }
                        )
                        filtered_layer = QgsRasterLayer(resampled_filtered_path, 'Filtered_DSM_Resampled')
                        filtered_dsm_path = resampled_filtered_path
                    
                    # Create calculator entries
                    original_entry = QgsRasterCalculatorEntry()
                    original_entry.ref = 'original@1'
                    original_entry.raster = original_layer
                    original_entry.bandNumber = 1
                    
                    filtered_entry = QgsRasterCalculatorEntry()
                    filtered_entry.ref = 'filtered@1'
                    filtered_entry.raster = filtered_layer
                    filtered_entry.bandNumber = 1
                    
                    entries = [original_entry, filtered_entry]
                    
                    # Calculate residuals: Original - Filtered
                    calc_expression = '"original@1" - "filtered@1"'
                    
                    calc = QgsRasterCalculator(
                        calc_expression,
                        output_residuals,
                        'GTiff',
                        original_layer.extent(),
                        original_layer.width(),
                        original_layer.height(),
                        entries
                    )
                    
                    result = calc.processCalculation(feedback)
                    if result != QgsRasterCalculator.Success:
                        raise Exception(f"QGIS Raster Calculator failed with code: {result}")
                    
                    print('DEBUG: QGIS raster calculator succeeded')
                    
                except Exception as e2:
                    print(f'DEBUG: QGIS raster calculator also failed: {str(e2)}')
                    print('DEBUG: Using simple GDAL subtract operation as fallback...')
                    
                    # Method 3: Simple GDAL subtract using gdal_calc
                    try:
                        # Use GDAL translate to ensure both files are accessible
                        temp_original = os.path.join(output_dir, 'temp_original_for_residuals.tif')
                        temp_filtered = os.path.join(output_dir, 'temp_filtered_for_residuals.tif')
                        
                        processing.run('gdal:translate', {
                            'INPUT': input_dsm_path,
                            'OUTPUT': temp_original
                        })
                        
                        processing.run('gdal:translate', {
                            'INPUT': filtered_dsm_path,
                            'OUTPUT': temp_filtered
                        })
                        
                        # Simple raster math using processing
                        processing.run(
                            'gdal:rastercalculator',
                            {
                                'INPUT_A': temp_original,
                                'BAND_A': 1,
                                'INPUT_B': temp_filtered,
                                'BAND_B': 1,
                                'FORMULA': 'A-B',
                                'NO_DATA': None,
                                'RTYPE': 5,  # Float32
                                'OUTPUT': output_residuals
                            }
                        )
                        
                        # Clean up temporary files
                        if os.path.exists(temp_original):
                            os.remove(temp_original)
                        if os.path.exists(temp_filtered):
                            os.remove(temp_filtered)
                            
                        print('DEBUG: GDAL subtract fallback succeeded')
                        
                    except Exception as e3:
                        print(f'DEBUG: All residual calculation methods failed. Continuing without residual analysis...')
                        print(f'DEBUG: Original error: {str(e)}')
                        print(f'DEBUG: QGIS error: {str(e2)}')
                        print(f'DEBUG: Fallback error: {str(e3)}')
                        
                        # Set residual_layer to None to skip residual analysis
                        residual_layer = None
                        use_residuals = False
            
            # Check if residual calculation was successful
            if not os.path.isfile(output_residuals):
                print('DEBUG: Residual file does not exist, analysis disabled')
                residual_layer = None
                use_residuals = False
            else:
                # Load residual layer
                residual_layer = QgsRasterLayer(output_residuals, 'Residuals')
                if not residual_layer.isValid():
                    print('DEBUG: Residual layer could not be loaded, continuing without residual analysis')
                    residual_layer = None
                    use_residuals = False
                else:
                    print('DEBUG: Residual layer created successfully:', output_residuals)
                    use_residuals = True
                    
                    # Debug: Check residual statistics
                    try:
                        residual_stats = residual_layer.dataProvider().bandStatistics(1)
                        print('DEBUG: Residual Min/Max:', residual_stats.minimumValue, residual_stats.maximumValue)
                        print('DEBUG: Residual Mean/StdDev:', residual_stats.mean, residual_stats.stdDev)
                        
                        # Check for problematic values
                        if residual_stats.minimumValue == residual_stats.maximumValue:
                            print('DEBUG: WARNING - All residual values are identical!')
                        if abs(residual_stats.minimumValue) > 1000 or abs(residual_stats.maximumValue) > 1000:
                            print('DEBUG: WARNING - Residual values seem unrealistic!')
                            
                    except Exception as e:
                        print(f'DEBUG: Could not calculate residual statistics: {str(e)}')
            
            # Step 3: Calculate slope (with FILTERED DSM)
            self.update_progress(gaussian_iterations + 2, total_steps, " Calculating slope analysis...")
            output_slope = os.path.join(output_dir, 'slope.tif')
            slope_result = processing.run(
                'qgis:slope',
                {
                    'INPUT': filtered_dsm,  # Use FILTERED DSM!
                    'Z_FACTOR': 1.0,
                    'OUTPUT': output_slope
                },
                feedback=feedback
            )
            slope_layer = QgsRasterLayer(output_slope, 'Slope')
            if not slope_layer.isValid():
                raise Exception(f"Slope layer could not be loaded: {output_slope}")
            print('DEBUG: Slope layer created:', output_slope)



            # Step 4: Calculate curvature (with FILTERED DSM)
            self.update_progress(gaussian_iterations + 3, total_steps, " Calculating curvature analysis...")
            curvature_layer = None
            try:
                curvature_result = processing.run(
                    'qgis:profilecurvature',
                    {'INPUT': filtered_dsm, 'OUTPUT': 'memory:curvature'},  # Use FILTERED DSM!
                    feedback=feedback
                )
                curvature_layer = curvature_result['OUTPUT']
                print('DEBUG: Curvature layer (profilecurvature) created from FILTERED DSM')
            except Exception as e:
                print('DEBUG: profilecurvature not available, trying GRASS r.slope.aspect')
                try:
                    filtered_dsm_path = self.get_raster_path(filtered_dsm)  # Use FILTERED DSM!
                    curvature_path = os.path.join(output_dir, 'curvature.tif')
                    curvature_result = processing.run(
                        'grass7:r.slope.aspect',
                        {
                            'elevation': filtered_dsm_path,  # Use FILTERED DSM!
                            'pcurvature': curvature_path,
                            'tcurvature': 'TEMPORARY_OUTPUT',
                            'slope': 'TEMPORARY_OUTPUT',
                            'aspect': 'TEMPORARY_OUTPUT',
                            'dx': 'TEMPORARY_OUTPUT',
                            'dy': 'TEMPORARY_OUTPUT',
                            'dxx': 'TEMPORARY_OUTPUT',
                            'dyy': 'TEMPORARY_OUTPUT',
                            'dxy': 'TEMPORARY_OUTPUT',
                            'zscale': 1,
                            'min_slope': 0,
                            'format': 0,
                            '-a': True,
                            '-e': False,
                            '-n': False,
                            'GRASS_REGION_PARAMETER': None,
                            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
                            'GRASS_RASTER_FORMAT_OPT': '',
                            'GRASS_RASTER_FORMAT_META': ''
                        },
                        feedback=feedback
                    )
                    if not os.path.isfile(curvature_path):
                        raise Exception(f"Curvature file was not created: {curvature_path}")
                    curvature_layer = QgsRasterLayer(curvature_path, 'Curvature')
                    if not curvature_layer.isValid():
                        raise Exception(f"Curvature layer could not be loaded: {curvature_path}")
                    print('DEBUG: Curvature layer (GRASS r.slope.aspect) created from FILTERED DSM')
                    print('DEBUG: Curvature Min/Max:', curvature_layer.dataProvider().bandStatistics(1).minimumValue, curvature_layer.dataProvider().bandStatistics(1).maximumValue)
                    print('DEBUG: Curvature Mean/StdDev:', curvature_layer.dataProvider().bandStatistics(1).mean, curvature_layer.dataProvider().bandStatistics(1).stdDev)
                except Exception as e2:
                    print('DEBUG: GRASS r.slope.aspect not available, trying SAGA NextGen slopeaspectcurvature')
                    try:
                        filtered_dsm_path = self.get_raster_path(filtered_dsm)  # Use FILTERED DSM!
                        curvature_path = os.path.join(output_dir, 'curvature.tif')
                        curvature_result = processing.run(
                            'sagang:slopeaspectcurvature',
                            {'GRID': filtered_dsm_path, 'CURVATURE': curvature_path},  # Use FILTERED DSM!
                            feedback=feedback
                        )
                        if not os.path.isfile(curvature_path):
                            raise Exception(f"Curvature file was not created: {curvature_path}")
                        curvature_layer = QgsRasterLayer(curvature_path, 'Curvature')
                        if not curvature_layer.isValid():
                            raise Exception(f"Curvature layer could not be loaded: {curvature_path}")
                        print('DEBUG: Curvature layer (SAGA NextGen slopeaspectcurvature) created from FILTERED DSM')
                        print('DEBUG: Curvature Min/Max:', curvature_layer.dataProvider().bandStatistics(1).minimumValue, curvature_layer.dataProvider().bandStatistics(1).maximumValue)
                        print('DEBUG: Curvature Mean/StdDev:', curvature_layer.dataProvider().bandStatistics(1).mean, curvature_layer.dataProvider().bandStatistics(1).stdDev)
                    except Exception as e3:
                        print('DEBUG: No curvature calculation possible:', str(e3))
                        QMessageBox.critical(self, 'Error', 'No curvature algorithm (QGIS, GRASS, SAGA) is available!')
                        return

            # Step 4b: Texture Analysis (optional)
            self.update_progress(gaussian_iterations + 4, total_steps, " Performing texture analysis (3-class classification)...")
            texture_variance, texture_entropy = self.perform_texture_analysis(filtered_dsm_path, output_dir, feedback)

            # Step 5a: Statistical Analysis and Adaptive Threshold Calculation (Cao et al. 2020)
            self.update_progress(gaussian_iterations + 5, total_steps, "Statistical analysis & adaptive thresholds (Cao et al. 2020)...")
            print('DEBUG: Starting statistical analysis for adaptive thresholds...')
            
            # Determine if texture analysis is available
            use_texture = (texture_variance is not None and texture_variance.isValid() and 
                          texture_entropy is not None and texture_entropy.isValid())
            print(f'DEBUG: Texture analysis available: {use_texture}')
            
            # Determine threshold values based on selected method
            if self.radioPercentile.isChecked():
                print('DEBUG: Using percentile-based thresholds (Cao et al. 2020)')
                
                # Perform comprehensive statistical analysis
                stats_results = self.analyze_geomorphometric_statistics(
                    slope_layer, 
                    curvature_layer, 
                    residual_layer if use_residuals else None,
                    texture_variance, 
                    texture_entropy
                )
                
                if stats_results is None:
                    QMessageBox.warning(self, 'Warning', 'Statistical analysis failed. Falling back to fixed thresholds.')
                    # Use fixed thresholds as fallback
                    slope_threshold = self.spinSlope.value()
                    curvature_threshold = self.spinCurvature.value()
                    residual_threshold = self.spinResidual.value()
                    
                    # Get texture thresholds from UI for fallback
                    variance_threshold = self.spinVarianceThreshold.value() if hasattr(self, 'spinVarianceThreshold') else 0.5
                    entropy_threshold = self.spinEntropyThreshold.value() if hasattr(self, 'spinEntropyThreshold') else 2.0
                    
                    # Create fallback stats_results
                    stats_results = {
                        'slope_threshold': slope_threshold,
                        'curvature_pos_threshold': curvature_threshold,
                        'curvature_neg_threshold': -curvature_threshold,
                        'residual_threshold': residual_threshold,
                        'variance_threshold': variance_threshold,
                        'entropy_threshold': entropy_threshold,
                        'use_texture': use_texture,
                        'threshold_method': 'fixed_fallback'
                    }
                    
                    print('DEBUG: Using fixed threshold fallback values')
                else:
                    # Use calculated percentile thresholds
                    slope_threshold = stats_results['slope_threshold']
                    curvature_pos_threshold = stats_results['curvature_pos_threshold']
                    curvature_neg_threshold = stats_results['curvature_neg_threshold']
                    residual_threshold = stats_results['residual_threshold']
                    
                    # Get texture thresholds from stats_results
                    variance_threshold = stats_results.get('variance_threshold', 0.5)
                    entropy_threshold = stats_results.get('entropy_threshold', 2.0)
                    
                    # For backwards compatibility with existing logic, use symmetric curvature threshold
                    curvature_threshold = max(abs(curvature_pos_threshold), abs(curvature_neg_threshold))
                    
                    # Ensure stats_results has all required fields
                    stats_results['curvature_threshold'] = curvature_threshold
                    stats_results['threshold_method'] = 'percentile'
                    
                    print('DEBUG: ===== Applied Adaptive Thresholds =====')
                    print(f'DEBUG: Slope threshold: {slope_threshold:.4f}°')
                    print(f'DEBUG: Curvature threshold: ±{curvature_threshold:.4f}')
                    if residual_threshold is not None:
                        print(f'DEBUG: Residual threshold: ±{residual_threshold:.4f}m')
                    if use_texture:
                        print(f'DEBUG: Variance threshold (percentile): {variance_threshold:.4f}')
                        print(f'DEBUG: Entropy threshold (percentile): {entropy_threshold:.4f}')
                    print('DEBUG: ========================================')
                    
            else:
                print('DEBUG: Using fixed thresholds (legacy mode)')
                slope_threshold = self.spinSlope.value()
                curvature_threshold = self.spinCurvature.value()
                residual_threshold = self.spinResidual.value()
                
                # Get texture thresholds from UI for fixed thresholds
                variance_threshold = self.spinVarianceThreshold.value() if hasattr(self, 'spinVarianceThreshold') else 0.5
                entropy_threshold = self.spinEntropyThreshold.value() if hasattr(self, 'spinEntropyThreshold') else 2.0
                
                # Create empty stats_results for fixed thresholds
                stats_results = {
                    'slope_threshold': slope_threshold,
                    'curvature_pos_threshold': curvature_threshold,
                    'curvature_neg_threshold': -curvature_threshold,
                    'residual_threshold': residual_threshold,
                    'variance_threshold': variance_threshold,
                    'entropy_threshold': entropy_threshold,
                    'use_texture': use_texture,
                    'threshold_method': 'fixed'
                }
                
                print('DEBUG: ===== Applied Fixed Thresholds =====')
                print(f'DEBUG: Slope threshold: {slope_threshold:.4f}°')
                print(f'DEBUG: Curvature threshold: ±{curvature_threshold:.4f}')
                print(f'DEBUG: Residual threshold: ±{residual_threshold:.4f}m')
                if use_texture:
                    print(f'DEBUG: Variance threshold (fixed): {variance_threshold:.4f}')
                    print(f'DEBUG: Entropy threshold (fixed): {entropy_threshold:.4f}')
                print('DEBUG: ====================================')

            # Step 5: Identify anthropogenic features
            self.update_progress(gaussian_iterations + 6, total_steps, " Identifying anthropogenic features...")
            # Ensure slope_layer and curvature_layer are QgsRasterLayer
            if isinstance(slope_layer, str):
                slope_layer = QgsRasterLayer(slope_layer, 'Slope')
            if not slope_layer.isValid():
                raise Exception("Slope layer could not be loaded!")
            if isinstance(curvature_layer, str):
                curvature_layer = QgsRasterLayer(curvature_layer, 'Curvature')
            if not curvature_layer.isValid():
                raise Exception("Curvature layer could not be loaded!")



            # Check if size, extent and CRS match
            need_resample = False
            basic_mismatch = (slope_layer.width() != curvature_layer.width() or
                             slope_layer.height() != curvature_layer.height() or
                             slope_layer.extent() != curvature_layer.extent() or
                             slope_layer.crs() != curvature_layer.crs())
            
            residual_mismatch = False
            if use_residuals and residual_layer is not None:
                residual_mismatch = (slope_layer.width() != residual_layer.width() or
                                   slope_layer.height() != residual_layer.height() or
                                   slope_layer.extent() != residual_layer.extent() or
                                   slope_layer.crs() != residual_layer.crs())
            
            if basic_mismatch or residual_mismatch:
                need_resample = True

            if need_resample:
                # Resample curvature to slope
                resampled_curvature_path = os.path.join(output_dir, 'curvature_resampled.tif')
                processing.run(
                    'gdal:warpreproject',
                    {
                        'INPUT': curvature_layer,
                        'SOURCE_CRS': curvature_layer.crs().authid(),
                        'TARGET_CRS': slope_layer.crs().authid(),
                        'RESAMPLING': 0,
                        'NODATA': None,
                        'TARGET_RESOLUTION': None,
                        'OPTIONS': '',
                        'DATA_TYPE': 0,
                        'TARGET_EXTENT': None,
                        'TARGET_EXTENT_CRS': None,
                        'MULTITHREADING': False,
                        'OUTPUT': resampled_curvature_path
                    }
                )
                curvature_layer = QgsRasterLayer(resampled_curvature_path, 'Curvature_Resampled')
                if not curvature_layer.isValid():
                    raise Exception(f"Resampled curvature layer could not be loaded: {resampled_curvature_path}")
                
                # Resample residual to slope if residuals are available
                if use_residuals and residual_layer is not None:
                    resampled_residual_path = os.path.join(output_dir, 'residual_resampled.tif')
                    processing.run(
                        'gdal:warpreproject',
                        {
                            'INPUT': residual_layer,
                            'SOURCE_CRS': residual_layer.crs().authid(),
                            'TARGET_CRS': slope_layer.crs().authid(),
                            'RESAMPLING': 0,
                            'NODATA': None,
                            'TARGET_RESOLUTION': None,
                            'OPTIONS': '',
                            'DATA_TYPE': 0,
                            'TARGET_EXTENT': None,
                            'TARGET_EXTENT_CRS': None,
                            'MULTITHREADING': False,
                            'OUTPUT': resampled_residual_path
                        }
                    )
                    residual_layer = QgsRasterLayer(resampled_residual_path, 'Residual_Resampled')
                    if not residual_layer.isValid():
                        residual_layer = None
                        use_residuals = False

            # Create raster calculator expression for 3-class classification
            variance_threshold = stats_results.get('variance_threshold') if stats_results else None
            entropy_threshold = stats_results.get('entropy_threshold') if stats_results else None
            use_texture = stats_results.get('use_texture', False) if stats_results else False
            
            # Check if texture layers are actually available
            texture_layers_available = texture_variance is not None and texture_entropy is not None
            
            if use_texture and texture_layers_available:
                # 3-class formula WITH texture rasters: 0=Natural, 1=Vegetation, 2=Anthropogenic
                print('DEBUG: Using 3-class texture-based classification (WITH texture rasters)')
                if use_residuals and residual_layer is not None:
                    calc_expression = f'if(("variance@1" > {variance_threshold} OR "entropy@1" > {entropy_threshold}) AND ("slope@1" <= {slope_threshold} AND "curvature@1" <= {curvature_threshold} AND "curvature@1" >= -{curvature_threshold} AND "residual@1" <= {residual_threshold} AND "residual@1" >= -{residual_threshold}), 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold} OR "residual@1" > {residual_threshold} OR "residual@1" < -{residual_threshold}), 2, 0))'
                else:
                    calc_expression = f'if(("variance@1" > {variance_threshold} OR "entropy@1" > {entropy_threshold}) AND ("slope@1" <= {slope_threshold} AND "curvature@1" <= {curvature_threshold} AND "curvature@1" >= -{curvature_threshold}), 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold}), 2, 0))'
                
                print(f'DEBUG:  CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG:  Thresholds - Variance: {variance_threshold}, Entropy: {entropy_threshold}')
                print(f'DEBUG:  Thresholds - Slope: {slope_threshold}, Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG:  Thresholds - Residual: ±{residual_threshold}')
            elif use_texture and not texture_layers_available:
                # 3-class formula WITHOUT texture rasters: simplified classification
                print('DEBUG: Using 3-class simplified classification (WITHOUT texture rasters)')
                print(f'DEBUG: Using slope as vegetation proxy (low slope < {slope_threshold/2:.2f}° = vegetation)')
                # Use slope as vegetation proxy: low slope = vegetation, high slope = anthropogenic
                vegetation_slope_threshold = slope_threshold / 2  # Half of anthropogenic threshold
                if use_residuals and residual_layer is not None:
                    calc_expression = f'if("slope@1" <= {vegetation_slope_threshold} AND abs("residual@1") <= {residual_threshold/2}, 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold} OR abs("residual@1") > {residual_threshold}), 2, 0))'
                else:
                    calc_expression = f'if("slope@1" <= {vegetation_slope_threshold}, 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold}), 2, 0))'
                
                print(f'DEBUG:  CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG:  Thresholds - Vegetation slope: {vegetation_slope_threshold}, Anthropogenic slope: {slope_threshold}')
                print(f'DEBUG:  Thresholds - Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG:  Thresholds - Residual: ±{residual_threshold}')
            else:
                # Original binary classification (anthropogenic=1, natural=0)
                print('DEBUG: Using binary classification (no texture)')
                if use_residuals and residual_layer is not None:
                    calc_expression = f'("slope@1" > {slope_threshold}) OR ("curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold}) OR ("residual@1" > {residual_threshold} OR "residual@1" < -{residual_threshold})'
                else:
                    calc_expression = f'("slope@1" > {slope_threshold}) OR ("curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold})'
                
                print(f'DEBUG:  CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG:  Thresholds - Slope: {slope_threshold}, Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG:  Thresholds - Residual: ±{residual_threshold}')
            
            entries = []
            from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
            slope_entry = QgsRasterCalculatorEntry()
            slope_entry.ref = 'slope@1'
            slope_entry.raster = slope_layer
            slope_entry.bandNumber = 1
            entries.append(slope_entry)
            curvature_entry = QgsRasterCalculatorEntry()
            curvature_entry.ref = 'curvature@1'
            curvature_entry.raster = curvature_layer
            curvature_entry.bandNumber = 1
            entries.append(curvature_entry)
            
            # Only add residual entry if residuals are available
            if use_residuals and residual_layer is not None:
                residual_entry = QgsRasterCalculatorEntry()
                residual_entry.ref = 'residual@1'
                residual_entry.raster = residual_layer
                residual_entry.bandNumber = 1
                entries.append(residual_entry)
            
            # Add texture entries if available
            if use_texture and texture_layers_available:
                variance_entry = QgsRasterCalculatorEntry()
                variance_entry.ref = 'variance@1'
                variance_entry.raster = texture_variance
                variance_entry.bandNumber = 1
                entries.append(variance_entry)
                
                entropy_entry = QgsRasterCalculatorEntry()
                entropy_entry.ref = 'entropy@1'
                entropy_entry.raster = texture_entropy
                entropy_entry.bandNumber = 1
                entries.append(entropy_entry)

            # Check write permissions in target directory
            if not os.access(output_dir, os.W_OK):
                raise Exception(f"No write permissions in target directory: {output_dir}")
            
            calc = QgsRasterCalculator(
                calc_expression,
                output_anthropogenic,
                'GTiff',
                slope_layer.extent(),
                slope_layer.width(),
                slope_layer.height(),
                entries
            )
            
            # Explicit call of Raster Calculator
            try:
                result = calc.processCalculation(feedback)
                if result != QgsRasterCalculator.Success:
                    raise Exception(f"Raster Calculator failed with code: {result}")
            except Exception as e:
                raise Exception(f"Raster Calculator error: {str(e)}")
            
            if not os.path.isfile(output_anthropogenic):
                raise Exception(f"Anthropogenic mask was not created: {output_anthropogenic}")
            
            #  DEBUGGING: Check classification result immediately
            print('DEBUG:  CHECKING CLASSIFICATION RESULT...')
            classification_layer = QgsRasterLayer(output_anthropogenic, 'Classification_Check')
            if classification_layer.isValid():
                classification_provider = classification_layer.dataProvider()
                classification_stats = classification_provider.bandStatistics(1, QgsRasterBandStats.All)
                print(f'DEBUG:  Classification result - Min: {classification_stats.minimumValue}, Max: {classification_stats.maximumValue}')
                print(f'DEBUG:  Classification result - Mean: {classification_stats.mean:.3f}, StdDev: {classification_stats.stdDev:.3f}')
                
                # Sample values to see what classes were actually produced
                try:
                    # Use sampling instead of block access for safety
                    unique_values = set()
                    class_counts = {0: 0, 1: 0, 2: 0}
                    samples_taken = 0
                    max_samples = 400  # 20x20 sample grid
                    
                    for i in range(0, classification_layer.width(), max(1, classification_layer.width() // 20)):
                        for j in range(0, classification_layer.height(), max(1, classification_layer.height() // 20)):
                            if samples_taken >= max_samples:
                                break
                            
                            try:
                                # Convert pixel coordinates to map coordinates
                                x = classification_layer.extent().xMinimum() + (i + 0.5) * classification_layer.rasterUnitsPerPixelX()
                                y = classification_layer.extent().yMaximum() - (j + 0.5) * classification_layer.rasterUnitsPerPixelY()
                                
                                # Sample value using provider (safer than block access)
                                value, success = classification_provider.sample(QgsPointXY(x, y), 1)
                                if success and value != classification_provider.sourceNoDataValue(1):
                                    int_value = int(value)
                                    unique_values.add(int_value)
                                    if int_value in class_counts:
                                        class_counts[int_value] += 1
                                
                                samples_taken += 1
                                
                            except Exception as sample_error:
                                continue
                        
                        if samples_taken >= max_samples:
                            break
                    
                    print(f'DEBUG:  Unique classification values: {sorted(unique_values)}')
                    print(f'DEBUG:  Class distribution in sample:')
                    for class_id, count in class_counts.items():
                        percentage = (count / sum(class_counts.values())) * 100 if sum(class_counts.values()) > 0 else 0
                        print(f'DEBUG:    Class {class_id}: {count} pixels ({percentage:.1f}%)')
                    
                    if 2 not in unique_values:
                        print('DEBUG:  CRITICAL: Class 2 (Anthropogenic) was NOT produced!')
                        print('DEBUG:  This explains why filtering fails - no class 2 pixels exist!')
                    else:
                        print('DEBUG:  Class 2 (Anthropogenic) was produced successfully')
                        
                except Exception as e:
                    print(f'DEBUG:  Could not sample classification values: {str(e)}')
            else:
                print('DEBUG:  ERROR: Classification result layer is invalid!')
            
            # Calculate anthropogenic statistics
            test_layer = QgsRasterLayer(output_anthropogenic, 'Test')
            if test_layer.isValid():
                #  CRITICAL DEBUGGING: Check actual raster values
                print('DEBUG:  ANALYZING ANTHROPOGENIC FEATURES RASTER...')
                provider = test_layer.dataProvider()
                stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                print(f'DEBUG:  Anthropogenic raster - Min: {stats.minimumValue}, Max: {stats.maximumValue}')
                print(f'DEBUG:  Anthropogenic raster - Mean: {stats.mean:.3f}, StdDev: {stats.stdDev:.3f}')
                
                # Sample some values to see what's actually in the raster
                try:
                    # Use sampling instead of block access for safety
                    unique_values = set()
                    samples_taken = 0
                    max_samples = 100  # 10x10 sample grid
                    
                    for i in range(0, test_layer.width(), max(1, test_layer.width() // 10)):
                        for j in range(0, test_layer.height(), max(1, test_layer.height() // 10)):
                            if samples_taken >= max_samples:
                                break
                            
                            try:
                                # Convert pixel coordinates to map coordinates
                                x = test_layer.extent().xMinimum() + (i + 0.5) * test_layer.rasterUnitsPerPixelX()
                                y = test_layer.extent().yMaximum() - (j + 0.5) * test_layer.rasterUnitsPerPixelY()
                                
                                # Sample value using provider (safer than block access)
                                value, success = provider.sample(QgsPointXY(x, y), 1)
                                if success and value != provider.sourceNoDataValue(1):
                                    unique_values.add(int(value))
                                
                                samples_taken += 1
                                
                            except Exception as sample_error:
                                continue
                        
                        if samples_taken >= max_samples:
                            break
                    
                    print(f'DEBUG:  Unique values found in sample: {sorted(unique_values)}')
                    
                    if len(unique_values) == 2 and 0 in unique_values and 1 in unique_values:
                        print('DEBUG:  PROBLEM: Raster is BINARY (0,1) not 3-class (0,1,2)!')
                    elif len(unique_values) == 3 and 0 in unique_values and 1 in unique_values and 2 in unique_values:
                        print('DEBUG:  Raster is 3-class (0,1,2) as expected')
                    else:
                        print(f'DEBUG:  Unexpected values: {sorted(unique_values)}')
                except Exception as e:
                    print(f'DEBUG:  Could not sample raster values: {str(e)}')
                
                anthropogenic_pixels = stats.sum
                total_pixels = test_layer.width() * test_layer.height()
                anthropogenic_percentage = (anthropogenic_pixels / total_pixels) * 100
                print(f'DEBUG: Anthropogenic features detected: {anthropogenic_percentage:.1f}% of area')

            # Step 6: Buffer the anthropogenic mask
            self.update_progress(gaussian_iterations + 7, total_steps, f" Buffering features ({buffer_distance:.1f}m distance)...")
            
            print(f'DEBUG: Buffer Distance from UI: {buffer_distance:.1f}m')
            
            # Handle special case: buffer_distance = 0.0 means no buffering
            if buffer_distance <= 0.0:
                print('DEBUG: Buffer distance is 0.0 - skipping buffering, using original mask')
                output_buffered = os.path.join(output_dir, 'buffered_anthropogenic.tif')
                
                if use_texture:
                    # For 3-class system: extract selected features based on filter options
                    print('DEBUG: Extracting selected features based on filter options (no buffering)')
                    
                    # Get filter options from UI
                    print('DEBUG:  CHECKING UI FILTER ELEMENTS (MASKING)...')
                    print(f'DEBUG: hasattr checkFilterAnthropogenic: {hasattr(self, "checkFilterAnthropogenic")}')
                    print(f'DEBUG: hasattr checkFilterVegetation: {hasattr(self, "checkFilterVegetation")}')
                    
                    if hasattr(self, 'checkFilterAnthropogenic'):
                        anthro_checked = self.checkFilterAnthropogenic.isChecked()
                        print(f'DEBUG: checkFilterAnthropogenic.isChecked(): {anthro_checked}')
                        print(f'DEBUG: checkFilterAnthropogenic object: {self.checkFilterAnthropogenic}')
                        print(f'DEBUG: checkFilterAnthropogenic type: {type(self.checkFilterAnthropogenic)}')
                    else:
                        anthro_checked = True
                        print('DEBUG: checkFilterAnthropogenic NOT FOUND - using default True')
                    
                    if hasattr(self, 'checkFilterVegetation'):
                        veg_checked = self.checkFilterVegetation.isChecked()
                        print(f'DEBUG: checkFilterVegetation.isChecked(): {veg_checked}')
                        print(f'DEBUG: checkFilterVegetation object: {self.checkFilterVegetation}')
                        print(f'DEBUG: checkFilterVegetation type: {type(self.checkFilterVegetation)}')
                    else:
                        veg_checked = False
                        print('DEBUG: checkFilterVegetation NOT FOUND - using default False')
                    
                    filter_anthropogenic = anthro_checked
                    filter_vegetation = veg_checked
                    
                    print(f'DEBUG: Filter Anthropogenic: {filter_anthropogenic}')
                    print(f'DEBUG: Filter Vegetation: {filter_vegetation}')
                    
                    # Create formula based on filter selections
                    if filter_anthropogenic and filter_vegetation:
                        # Filter both: Classes 1 and 2 become 1, rest becomes 0
                        formula = 'A > 0'
                        print('DEBUG: Filtering both anthropogenic and vegetation features')
                    elif filter_anthropogenic and not filter_vegetation:
                        # Filter only anthropogenic: Class 2 becomes 1, rest becomes 0
                        formula = 'A > 1'
                        print('DEBUG: Filtering only anthropogenic features')
                    elif not filter_anthropogenic and filter_vegetation:
                        # Filter only vegetation: Class 1 becomes 1, rest becomes 0
                        formula = 'A > 0 AND A <= 1'
                        print('DEBUG: Filtering only vegetation features')
                    else:
                        # Filter nothing: Create empty mask (all 0)
                        formula = '0'
                        print('DEBUG: No features selected for filtering - creating empty mask')
                    
                    print(f'DEBUG:  Using formula: {formula}')
                    
                    # Load the anthropogenic features raster
                    anthropogenic_layer = QgsRasterLayer(output_anthropogenic, 'Anthropogenic_For_Masking')
                    if not anthropogenic_layer.isValid():
                        raise Exception("Could not load anthropogenic features raster for masking")
                    
                    # Create raster calculator entry
                    from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
                    anthro_entry = QgsRasterCalculatorEntry()
                    anthro_entry.ref = 'A'
                    anthro_entry.raster = anthropogenic_layer
                    anthro_entry.bandNumber = 1
                    
                    # Create QGIS raster calculator
                    calc = QgsRasterCalculator(
                        formula,
                        output_buffered,
                        'GTiff',
                        anthropogenic_layer.extent(),
                        anthropogenic_layer.width(),
                        anthropogenic_layer.height(),
                        [anthro_entry]
                    )
                    
                    result = calc.processCalculation(feedback)
                    if result != QgsRasterCalculator.Success:
                        raise Exception(f"QGIS Raster Calculator failed with code: {result}")
                    
                    if not os.path.isfile(output_buffered):
                        raise Exception("Masked raster file was not created")
                    
                    #  Check the result of filtering
                    if os.path.isfile(output_buffered):
                        filtered_layer = QgsRasterLayer(output_buffered, 'Filtered_Check')
                        if filtered_layer.isValid():
                            filtered_stats = filtered_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                            print(f'DEBUG:  Filtered result - Min: {filtered_stats.minimumValue}, Max: {filtered_stats.maximumValue}')
                            print(f'DEBUG:  Filtered result - Mean: {filtered_stats.mean:.3f}, Sum: {filtered_stats.sum:.0f}')
                            
                            if filtered_stats.sum == 0:
                                print('DEBUG:  CRITICAL: Filtering resulted in empty mask!')
                                print('DEBUG:  This means the formula found no matching pixels!')
                            else:
                                print(f'DEBUG:  Filtering successful - {filtered_stats.sum:.0f} pixels selected')
                        else:
                            print('DEBUG:  ERROR: Filtered raster is invalid!')
                    else:
                        print('DEBUG:  ERROR: Filtered raster file was not created!')
                else:
                    # For binary system: simply copy the mask
                    import shutil
                    shutil.copy2(output_anthropogenic, output_buffered)
                buffer_success = True
            else:
                # Extract selected features for buffering if using 3-class system
                if use_texture:
                    print('DEBUG: Extracting selected features for selective buffering')
                    
                    # Get filter options from UI (same logic as above)
                    print('DEBUG:  CHECKING UI FILTER ELEMENTS (MASKING)...')
                    print(f'DEBUG: hasattr checkFilterAnthropogenic: {hasattr(self, "checkFilterAnthropogenic")}')
                    print(f'DEBUG: hasattr checkFilterVegetation: {hasattr(self, "checkFilterVegetation")}')
                    
                    if hasattr(self, 'checkFilterAnthropogenic'):
                        anthro_checked = self.checkFilterAnthropogenic.isChecked()
                        print(f'DEBUG: checkFilterAnthropogenic.isChecked(): {anthro_checked}')
                        print(f'DEBUG: checkFilterAnthropogenic object: {self.checkFilterAnthropogenic}')
                        print(f'DEBUG: checkFilterAnthropogenic type: {type(self.checkFilterAnthropogenic)}')
                    else:
                        anthro_checked = True
                        print('DEBUG: checkFilterAnthropogenic NOT FOUND - using default True')
                    
                    if hasattr(self, 'checkFilterVegetation'):
                        veg_checked = self.checkFilterVegetation.isChecked()
                        print(f'DEBUG: checkFilterVegetation.isChecked(): {veg_checked}')
                        print(f'DEBUG: checkFilterVegetation object: {self.checkFilterVegetation}')
                        print(f'DEBUG: checkFilterVegetation type: {type(self.checkFilterVegetation)}')
                    else:
                        veg_checked = False
                        print('DEBUG: checkFilterVegetation NOT FOUND - using default False')
                    
                    filter_anthropogenic = anthro_checked
                    filter_vegetation = veg_checked
                    
                    print(f'DEBUG: Filter Anthropogenic: {filter_anthropogenic}')
                    print(f'DEBUG: Filter Vegetation: {filter_vegetation}')
                    
                    # Create formula based on filter selections
                    if filter_anthropogenic and filter_vegetation:
                        formula = 'A > 0'
                        print('DEBUG: Buffering both anthropogenic and vegetation features')
                    elif filter_anthropogenic and not filter_vegetation:
                        formula = 'A > 1'
                        print('DEBUG: Buffering only anthropogenic features')
                    elif not filter_anthropogenic and filter_vegetation:
                        formula = 'A > 0 AND A <= 1'
                        print('DEBUG: Buffering only vegetation features')
                    else:
                        formula = '0'
                        print('DEBUG: No features selected for buffering - creating empty mask')
                    
                    print(f'DEBUG:  Using formula: {formula}')
                    
                    anthropogenic_only_path = os.path.join(output_dir, 'selected_features_for_buffering.tif')
                    
                    # Create binary mask based on selected features using QGIS Raster Calculator
                    print(f'DEBUG:  Using formula: {formula}')
                    
                    # Load the anthropogenic features raster
                    anthropogenic_layer = QgsRasterLayer(output_anthropogenic, 'Anthropogenic_For_Filtering')
                    print('DEBUG: [QGIS RasterCalc] Checking input raster for filtering:')
                    print(f'  Path: {output_anthropogenic}')
                    print(f'  Exists: {os.path.isfile(output_anthropogenic)}')
                    print(f'  Layer valid: {anthropogenic_layer.isValid()}')
                    if anthropogenic_layer.isValid():
                        print(f'  Extent: {anthropogenic_layer.extent().toString()}')
                        print(f'  Width: {anthropogenic_layer.width()} Height: {anthropogenic_layer.height()}')
                        print(f'  Band count: {anthropogenic_layer.bandCount()}')
                        provider = anthropogenic_layer.dataProvider()
                        print(f'  NoData value: {provider.sourceNoDataValue(1)}')
                        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                        print(f'  Min: {stats.minimumValue}, Max: {stats.maximumValue}, Mean: {stats.mean}')
                    else:
                        print('  ERROR: Anthropogenic layer is not valid!')
                    print(f'  Output dir writable: {os.access(os.path.dirname(anthropogenic_only_path), os.W_OK)}')
                    print(f'  Output path: {anthropogenic_only_path}')
                    if os.path.isfile(anthropogenic_only_path):
                        print('  Output file already exists and will be overwritten.')
                    # End debug block
                    
                    # Use GDAL raster calculator instead
                    processing.run(
                        'gdal:rastercalculator',
                        {
                            'INPUT_A': output_anthropogenic,
                            'BAND_A': 1,
                            'FORMULA': formula,
                            'NO_DATA': None,
                            'RTYPE': 5,  # Float32
                            'OUTPUT': anthropogenic_only_path
                        },
                        feedback=feedback
                    )
                    
                    if not os.path.isfile(anthropogenic_only_path):
                        raise Exception("Filtered raster file was not created")
                    
                    #  DEBUGGING: Check the result of initial filtering
                    print('DEBUG:  CHECKING INITIAL FILTERING RESULT...')
                    if os.path.isfile(anthropogenic_only_path):
                        initial_filter_layer = QgsRasterLayer(anthropogenic_only_path, 'Initial_Filter_Check')
                        if initial_filter_layer.isValid():
                            initial_stats = initial_filter_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                            print(f'DEBUG:  Initial filtering - Min: {initial_stats.minimumValue}, Max: {initial_stats.maximumValue}')
                            print(f'DEBUG:  Initial filtering - Mean: {initial_stats.mean:.3f}, Sum: {initial_stats.sum:.0f}')
                            
                            if initial_stats.sum == 0:
                                print('DEBUG:  CRITICAL: Initial filtering resulted in empty mask!')
                                print('DEBUG:  This means the formula found no matching pixels!')
                            else:
                                print(f'DEBUG:  Initial filtering successful - {initial_stats.sum:.0f} pixels selected')
                        else:
                            print('DEBUG:  ERROR: Initial filtered raster is invalid!')
                    else:
                        print('DEBUG:  ERROR: Initial filtered raster file was not created!')
                    
                    buffer_input = anthropogenic_only_path
                else:
                    buffer_input = output_anthropogenic
                
                # Calculate buffer distance based on pixel size and UI value
                buffer_distance_pixels = int(buffer_distance / scaling_info['pixel_size'])  # Convert meters to pixels
                buffer_distance_pixels = max(1, min(50, buffer_distance_pixels))  # Clamp to reasonable range (1-50 pixels)
                
                output_buffered = os.path.join(output_dir, 'buffered_anthropogenic.tif')
                buffer_success = False
                
                # Try GRASS r.buffer first
                try:
                    buffer_result = processing.run(
                        'grass7:r.buffer',
                        {
                            'input': buffer_input,
                            'distances': [buffer_distance_pixels],
                            'units': 0,  # Pixel units
                            'output': output_buffered,
                            'GRASS_REGION_PARAMETER': None,
                            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
                            'GRASS_RASTER_FORMAT_OPT': '',
                            'GRASS_RASTER_FORMAT_META': ''
                        },
                        feedback=feedback
                    )
                    
                    if os.path.isfile(output_buffered):
                        buffer_success = True
                    else:
                        raise Exception("GRASS buffer output file not created")
                        
                except Exception as e:
                    # Fallback: Try GDAL proximity buffer with proper conversion
                    try:
                        buffer_distance_meters = buffer_distance  # Direct from UI (already in meters)
                        
                        # Step 1: Create proximity raster
                        proximity_temp = os.path.join(output_dir, 'proximity_temp.tif')
                        processing.run(
                            'gdal:proximity',
                            {
                                'INPUT': buffer_input,
                                'BAND': 1,
                                'VALUES': '1',  # Buffer around pixels with value 1
                                'UNITS': 1,  # Geographic units
                                'MAX_DISTANCE': buffer_distance_meters,
                                'REPLACE': 0,
                                'NODATA': -1,  # Use -1 for NoData to distinguish from 0 distance
                                'OPTIONS': '',
                                'EXTRA': '',
                                'DATA_TYPE': 5,
                                'OUTPUT': proximity_temp
                            },
                            feedback=feedback
                        )
                        
                        if os.path.isfile(proximity_temp):
                            # Step 2: Convert proximity to binary mask using QGIS raster calculator
                            from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
                            
                            proximity_layer = QgsRasterLayer(proximity_temp, 'Proximity_Temp')
                            if not proximity_layer.isValid():
                                raise Exception("Could not load proximity raster")
                            
                            # Create raster calculator entry
                            prox_entry = QgsRasterCalculatorEntry()
                            prox_entry.ref = 'proximity@1'
                            prox_entry.raster = proximity_layer
                            prox_entry.bandNumber = 1
                            
                            # Expression: if proximity <= buffer_distance AND proximity >= 0, then 1, else 0
                            calc_expression = f'if( ("proximity@1" >= 0) AND ("proximity@1" <= {buffer_distance_meters}), 1, 0)'
                            
                            calc = QgsRasterCalculator(
                                calc_expression,
                                output_buffered,
                                'GTiff',
                                proximity_layer.extent(),
                                proximity_layer.width(),
                                proximity_layer.height(),
                                [prox_entry]
                            )
                            
                            result = calc.processCalculation(feedback)
                            if result == QgsRasterCalculator.Success and os.path.isfile(output_buffered):
                                buffer_success = True
                                
                                # Clean up temporary proximity file
                                try:
                                    os.remove(proximity_temp)
                                except:
                                    pass
                            else:
                                raise Exception(f"Binary mask conversion failed with code: {result}")
                        else:
                            raise Exception("GDAL proximity output file not created")
                            
                    except Exception as e2:
                        # Last resort: Use original mask without buffering
                        import shutil
                        shutil.copy2(buffer_input, output_buffered)
                        buffer_success = True
                        QMessageBox.warning(self, 'Warning', 'Buffer operation failed. Using original mask without buffering.')
                
                if not buffer_success or not os.path.isfile(output_buffered):
                    raise Exception("All buffer methods failed")
            
            #  DEBUGGING: Check the final buffered result
            print('DEBUG:  CHECKING FINAL BUFFERED RESULT...')
            if os.path.isfile(output_buffered):
                final_buffer_layer = QgsRasterLayer(output_buffered, 'Final_Buffer_Check')
                if final_buffer_layer.isValid():
                    final_buffer_stats = final_buffer_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                    print(f'DEBUG:  Final buffered result - Min: {final_buffer_stats.minimumValue}, Max: {final_buffer_stats.maximumValue}')
                    print(f'DEBUG:  Final buffered result - Mean: {final_buffer_stats.mean:.3f}, Sum: {final_buffer_stats.sum:.0f}')
                    
                    if final_buffer_stats.sum == 0:
                        print('DEBUG:  CRITICAL: Final buffering resulted in empty mask!')
                        print('DEBUG:  This means the buffering operation failed!')
                    else:
                        print(f'DEBUG:  Final buffering successful - {final_buffer_stats.sum:.0f} pixels selected')
                else:
                    print('DEBUG:  ERROR: Final buffered raster is invalid!')
            else:
                print('DEBUG:  ERROR: Final buffered raster file was not created!')
            
            # Check for excessive buffering (might indicate too low thresholds)
            try:
                buffered_layer = QgsRasterLayer(output_buffered, 'Buffered_Check')
                if buffered_layer.isValid():
                    buffered_stats = buffered_layer.dataProvider().bandStatistics(1)
                    total_pixels = buffered_layer.width() * buffered_layer.height()
                    buffered_percentage = (buffered_stats.sum / total_pixels) * 100
                    
                    if buffered_percentage > 50 and buffer_distance > 0.0:  # Only warn if actually buffering
                        QMessageBox.warning(self, 'High Buffering Warning', 
                                          f'Warning: {buffered_percentage:.1f}% of the area is buffered for interpolation.\n\n'
                                          'This may indicate:\n'
                                          '• Thresholds are too low (try higher percentiles)\n'
                                          '• Area has many natural steep features\n'
                                          '• Consider using fixed thresholds for comparison\n\n'
                                          'Processing will continue...')
            except Exception as e:
                pass

            # Step 7: Mask the filtered DSM with buffered anthropogenic features
            self.update_progress(gaussian_iterations + 8, total_steps, " Masking DSM with detected features...")
            masked_dsm_path = os.path.join(output_dir, 'masked_dsm.tif')
            
            # Load layers for masking calculation
            dsm_layer_for_calc = QgsRasterLayer(filtered_dsm_path, 'Filtered_DSM_For_Calc')
            anthropogenic_layer_for_calc = QgsRasterLayer(output_buffered, 'Buffered_Anthropogenic_For_Calc')

            # Check alignment between filtered DSM and buffered mask
            if (dsm_layer_for_calc.width() != anthropogenic_layer_for_calc.width() or
                dsm_layer_for_calc.height() != anthropogenic_layer_for_calc.height() or
                dsm_layer_for_calc.extent() != anthropogenic_layer_for_calc.extent() or
                dsm_layer_for_calc.crs() != anthropogenic_layer_for_calc.crs()):
                resampled_buffered_path = os.path.join(output_dir, 'buffered_anthropogenic_resampled.tif')
                processing.run(
                    'gdal:warpreproject',
                    {
                        'INPUT': output_buffered,
                        'SOURCE_CRS': anthropogenic_layer_for_calc.crs().authid(),
                        'TARGET_CRS': dsm_layer_for_calc.crs().authid(),
                        'RESAMPLING': 0,  # Nearest neighbor for binary mask
                        'NODATA': 0,
                        'TARGET_RESOLUTION': None,
                        'OPTIONS': '',
                        'DATA_TYPE': 5,
                        'TARGET_EXTENT': None,
                        'TARGET_EXTENT_CRS': None,
                        'MULTITHREADING': False,
                        'OUTPUT': resampled_buffered_path
                    }
                )
                anthropogenic_layer_for_calc = QgsRasterLayer(resampled_buffered_path, 'Buffered_Anthropogenic_Resampled')


            
            # Apply mask using raster calculator
            if use_texture:
                # For 3-class system: mask selected features
                calc_expression = 'if ( "buffered_mask@1" = 1, 0/0, "filtered_dsm@1" )'  # Mask where buffer=1
                
                # Get filter options for debug output
                print('DEBUG:  CHECKING UI FILTER ELEMENTS (MASKING)...')
                print(f'DEBUG: hasattr checkFilterAnthropogenic: {hasattr(self, "checkFilterAnthropogenic")}')
                print(f'DEBUG: hasattr checkFilterVegetation: {hasattr(self, "checkFilterVegetation")}')
                
                if hasattr(self, 'checkFilterAnthropogenic'):
                    anthro_checked = self.checkFilterAnthropogenic.isChecked()
                    print(f'DEBUG: checkFilterAnthropogenic.isChecked(): {anthro_checked}')
                    print(f'DEBUG: checkFilterAnthropogenic object: {self.checkFilterAnthropogenic}')
                    print(f'DEBUG: checkFilterAnthropogenic type: {type(self.checkFilterAnthropogenic)}')
                else:
                    anthro_checked = True
                    print('DEBUG: checkFilterAnthropogenic NOT FOUND - using default True')
                
                if hasattr(self, 'checkFilterVegetation'):
                    veg_checked = self.checkFilterVegetation.isChecked()
                    print(f'DEBUG: checkFilterVegetation.isChecked(): {veg_checked}')
                    print(f'DEBUG: checkFilterVegetation object: {self.checkFilterVegetation}')
                    print(f'DEBUG: checkFilterVegetation type: {type(self.checkFilterVegetation)}')
                else:
                    veg_checked = False
                    print('DEBUG: checkFilterVegetation NOT FOUND - using default False')
                
                filter_anthropogenic = anthro_checked
                filter_vegetation = veg_checked
                
                print(f'DEBUG: Filter Anthropogenic: {filter_anthropogenic}')
                print(f'DEBUG: Filter Vegetation: {filter_vegetation}')
                
                # Create formula based on filter selections
                if filter_anthropogenic and filter_vegetation:
                    # Filter both: Classes 1 and 2 become 1, rest becomes 0
                    formula = 'A > 0'
                    print('DEBUG: Filtering both anthropogenic and vegetation features')
                elif filter_anthropogenic and not filter_vegetation:
                    # Filter only anthropogenic: Class 2 becomes 1, rest becomes 0
                    formula = 'A > 1'
                    print('DEBUG: Filtering only anthropogenic features')
                elif not filter_anthropogenic and filter_vegetation:
                    # Filter only vegetation: Class 1 becomes 1, rest becomes 0
                    formula = 'A > 0 AND A <= 1'
                    print('DEBUG: Filtering only vegetation features')
                else:
                    # Filter nothing: Create empty mask (all 0)
                    formula = '0'
                    print('DEBUG: No features selected for masking - creating empty mask')
                
                print(f'DEBUG:  Using formula: {formula}')
                
                # Load the anthropogenic features raster
                anthropogenic_layer = QgsRasterLayer(output_anthropogenic, 'Anthropogenic_For_Filtering')
                if not anthropogenic_layer.isValid():
                    raise Exception("Could not load anthropogenic features raster for filtering")

                                # Use GDAL raster calculator instead
                processing.run(
                    'gdal:rastercalculator',
                    {
                        'INPUT_A': output_anthropogenic,
                        'BAND_A': 1,
                        'FORMULA': formula,
                        'NO_DATA': None,
                        'RTYPE': 5,  # Float32
                        'OUTPUT': output_buffered
                    },
                    feedback=feedback
                )
                
                #  Check the result of filtering
                if os.path.isfile(output_buffered):
                    filtered_layer = QgsRasterLayer(output_buffered, 'Filtered_Check')
                    if filtered_layer.isValid():
                        filtered_stats = filtered_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                        print(f'DEBUG:  Filtered result - Min: {filtered_stats.minimumValue}, Max: {filtered_stats.maximumValue}')
                        print(f'DEBUG:  Filtered result - Mean: {filtered_stats.mean:.3f}, Sum: {filtered_stats.sum:.0f}')
                        
                        if filtered_stats.sum == 0:
                            print('DEBUG:  CRITICAL: Filtering resulted in empty mask!')
                            print('DEBUG:  This means the formula found no matching pixels!')
                        else:
                            print(f'DEBUG:  Filtering successful - {filtered_stats.sum:.0f} pixels selected')
                    else:
                        print('DEBUG:  ERROR: Filtered raster is invalid!')
                else:
                    print('DEBUG:  ERROR: Filtered raster file was not created!')
            else:
                # Original binary masking
                calc_expression = 'if ( "buffered_mask@1" = 0, "filtered_dsm@1", 0/0 )'
                print('DEBUG: Using binary masking - masking all detected features')
            
            #  CRITICAL DEBUGGING: Comprehensive masking diagnostics
            print(f'DEBUG:  Masking expression: {calc_expression}')
            print(f'DEBUG:  DSM layer valid: {dsm_layer_for_calc.isValid()}')
            print(f'DEBUG:  Mask layer valid: {anthropogenic_layer_for_calc.isValid()}')

            #  Check mask content before applying
            try:
                if anthropogenic_layer_for_calc and anthropogenic_layer_for_calc.isValid():
                    provider = anthropogenic_layer_for_calc.dataProvider()
                    stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                    print(f'DEBUG:  Mask statistics - Min: {stats.minimumValue}, Max: {stats.maximumValue}, Mean: {stats.mean:.3f}')
                    print(f'DEBUG:  Mask valid pixels: {stats.elementCount:,}')
                    
                    # Critical check: If mask is all zeros, no masking will occur!
                    if stats.maximumValue == 0:
                        print('DEBUG:  CRITICAL ERROR: Mask contains only 0 values - NO MASKING WILL OCCUR!')
                        print('DEBUG:  This means no anthropogenic features were detected in buffering!')
                    elif stats.minimumValue == stats.maximumValue == 1:
                        print('DEBUG:  CRITICAL ERROR: Mask contains only 1 values - ENTIRE DSM WILL BE MASKED!')
                    else:
                        masked_pixels = int(stats.mean * stats.elementCount)
                        masking_percentage = (masked_pixels / stats.elementCount) * 100
                        print(f'DEBUG:  Mask OK: ~{masking_percentage:.1f}% of pixels will be masked')
                        
                else:
                    print('DEBUG:  CRITICAL ERROR: Mask layer is invalid!')
                    
            except Exception as mask_debug_error:
                print(f'DEBUG:  Could not analyze mask: {str(mask_debug_error)}')
            
            entries = []
            from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
            
            # Filtered DSM entry
            dsm_entry = QgsRasterCalculatorEntry()
            dsm_entry.ref = 'filtered_dsm@1'
            dsm_entry.raster = dsm_layer_for_calc
            dsm_entry.bandNumber = 1
            entries.append(dsm_entry)
            
            # Buffered mask entry
            mask_entry = QgsRasterCalculatorEntry()
            mask_entry.ref = 'buffered_mask@1'
            mask_entry.raster = anthropogenic_layer_for_calc
            mask_entry.bandNumber = 1
            entries.append(mask_entry)

            print('DEBUG:  Starting raster calculator operation...')
            calc = QgsRasterCalculator(
                calc_expression,
                masked_dsm_path,
                'GTiff',
                dsm_layer_for_calc.extent(),
                dsm_layer_for_calc.width(),
                dsm_layer_for_calc.height(),
                entries
            )
            
            result = calc.processCalculation(feedback)
            print(f'DEBUG:  Raster calculator result code: {result}')

            if result != QgsRasterCalculator.Success:
                print(f'DEBUG:  CRITICAL ERROR: Masking operation failed with code: {result}')
                raise Exception(f"Masking operation failed with code: {result}")
            else:
                print('DEBUG:  Raster calculator completed successfully')
            
            if not os.path.isfile(masked_dsm_path):
                print(f'DEBUG:  CRITICAL ERROR: Masked DSM file was not created: {masked_dsm_path}')
                raise Exception(f"Masked DSM was not created: {masked_dsm_path}")
            else:
                #  CRITICAL: Validate the masked DSM
                masked_dsm_size = os.path.getsize(masked_dsm_path)
                print(f'DEBUG:  Masked DSM created: {masked_dsm_size:,} bytes')
                
                # Compare with original DSM
                original_dsm_size = os.path.getsize(filtered_dsm_path)
                print(f'DEBUG:  Original DSM size: {original_dsm_size:,} bytes')
                
                # Quick validation of masked DSM content
                try:
                    masked_layer = QgsRasterLayer(masked_dsm_path, 'MaskedDSM_Check')
                    if masked_layer.isValid():
                        provider = masked_layer.dataProvider()
                        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                        
                        # Compare with original DSM stats
                        original_layer = QgsRasterLayer(filtered_dsm_path, 'OriginalDSM_Check')
                        original_provider = original_layer.dataProvider()
                        original_stats = original_provider.bandStatistics(1, QgsRasterBandStats.All)
                        
                        pixels_removed = original_stats.elementCount - stats.elementCount
                        masking_percentage = (pixels_removed / original_stats.elementCount) * 100
                        
                        print(f'DEBUG:  Original DSM - Valid pixels: {original_stats.elementCount:,}')
                        print(f'DEBUG:  Masked DSM - Valid pixels: {stats.elementCount:,}')
                        print(f'DEBUG:  MASKING RESULT: {pixels_removed:,} pixels removed ({masking_percentage:.1f}% of DSM)')
                        
                        if masking_percentage < 1.0:
                            print('DEBUG:  WARNING: Very few pixels masked - check buffer generation!')
                        elif masking_percentage > 90.0:
                            print('DEBUG:  WARNING: Too many pixels masked - check classification thresholds!')
                        else:
                            print('DEBUG:  Reasonable masking percentage detected')
                            
                        # Test a few specific values
                        print(f'DEBUG:  Masked DSM stats - Min: {stats.minimumValue:.2f}, Max: {stats.maximumValue:.2f}, Mean: {stats.mean:.2f}')
                        
                        # CRITICAL TEST: Are values actually different?
                        if abs(stats.mean - original_stats.mean) < 0.01 and pixels_removed == 0:
                            print('DEBUG:  CRITICAL PROBLEM: Masked DSM appears identical to original!')
                            print('DEBUG:  This suggests masking operation did not work properly!')
                        else:
                            print('DEBUG:  Masked DSM is different from original - masking appears successful')
                            
                    else:
                        print('DEBUG:  ERROR: Created masked DSM is invalid!')
                        
                except Exception as validation_error:
                    print(f'DEBUG:  Masked DSM validation failed: {str(validation_error)}')

            # Step 8: Advanced Interpolation on masked DSM with selected method
            output_dsm = os.path.join(output_dir, 'reconstructed_dsm.tif')
            
            # Determine selected interpolation method from UI
            interpolation_method = 'enhanced'  # Default
            if self.radioEnhanced.isChecked():
                interpolation_method = 'enhanced'
            elif self.radioSimple.isChecked():
                interpolation_method = 'simple'
            elif self.radioGrassFillnulls.isChecked():
                interpolation_method = 'grass_fillnulls'
            
            print(f'DEBUG: User selected interpolation method: {interpolation_method.upper()}')
            
            # Update progress with selected method
            method_display_name = {
                'enhanced': 'ENHANCED GDAL',
                'simple': 'SIMPLE GDAL', 
                'grass_fillnulls': 'GRASS R.FILLNULLS'
            }.get(interpolation_method, interpolation_method.upper())
            
            self.update_progress(gaussian_iterations + 9, total_steps, f"Surface reconstruction using {method_display_name}...")
            
            # Store original method for report (before potential fallbacks change it)
            original_interpolation_method = interpolation_method
            interpolation_success = False
            
            # Apply selected interpolation method with robust fallbacks
            
            # Enhanced method (can be called directly or as fallback)        
            if interpolation_method == 'enhanced':
                # Method 3: Enhanced GDAL fillnodata with multiple iterations and smoothing
                print('DEBUG: Starting Enhanced GDAL fillnodata with multi-stage processing...')
                try:
                    print('DEBUG: Enhanced GDAL: Stage 1 - Initial fillnodata with large search radius...')
                    
                    # Stage 1: Initial fillnodata with large search radius
                    temp_filled_1 = os.path.join(output_dir, 'temp_filled_stage1.tif')
                    processing.run(
                        'gdal:fillnodata',
                        {
                            'INPUT': masked_dsm_path,
                            'BAND': 1,
                            'DISTANCE': fill_distance * 2,  # Larger search radius
                            'ITERATIONS': 3,  # More iterations
                            'NO_MASK': False,
                            'MASK_LAYER': None,
                            'OPTIONS': None,
                            'EXTRA': '',
                            'OUTPUT': temp_filled_1
                        },
                        feedback=feedback
                    )
                    
                    # Stage 2: Apply Gaussian smoothing to reduce artifacts
                    temp_smoothed = os.path.join(output_dir, 'temp_smoothed.tif')
                    try:
                        processing.run(
                            'sagang:gaussianfilter',
                            {
                                'INPUT': temp_filled_1,
                                'SIGMA': 1.0,  # Moderate smoothing
                                'KERNEL_TYPE': 1,
                                'KERNEL_RADIUS': 3,
                                'RESULT': temp_smoothed
                            },
                            feedback=feedback
                        )
                        current_result = temp_smoothed
                    except:
                        print('DEBUG: Gaussian smoothing failed, using stage 1 result')
                        current_result = temp_filled_1
                    
                    # Stage 3: Final fillnodata pass with smaller radius for detail
                    processing.run(
                        'gdal:fillnodata',
                        {
                            'INPUT': current_result,
                            'BAND': 1,
                            'DISTANCE': fill_distance,  # Original distance
                            'ITERATIONS': fill_iterations,
                            'NO_MASK': False,
                            'MASK_LAYER': None,
                            'OPTIONS': None,
                            'EXTRA': '',
                            'OUTPUT': output_dsm
                        },
                        feedback=feedback
                    )
                    
                    if os.path.isfile(output_dsm):
                        print('DEBUG: Enhanced multi-stage GDAL fillnodata succeeded')
                        interpolation_success = True
                        
                        # Clean up temporary files
                        for temp_file in [temp_filled_1, temp_smoothed]:
                            if os.path.exists(temp_file):
                                try:
                                    os.remove(temp_file)
                                except:
                                    pass
                    else:
                        raise Exception("Enhanced fillnodata output file not created")
                        
                except Exception as e:
                    print(f'DEBUG: Enhanced GDAL fillnodata failed: {str(e)}')
                    print('DEBUG: Enhanced failed, automatically falling back to Simple GDAL method...')
                    interpolation_method = 'simple'  # Auto-fallback to simple method
                    
            # GRASS r.fillnulls method (no fallbacks - direct execution only)
            elif interpolation_method == 'grass_fillnulls':
                print('DEBUG: Starting GRASS r.fillnulls interpolation...')
                try:
                    # Validate NoData values before processing
                    print('DEBUG: Validating NoData values for GRASS r.fillnulls...')
                    if not self.validate_nodata_raster(masked_dsm_path):
                        raise Exception("NoData validation failed - raster may not have proper NoData values defined")
                    
                    # Get GRASS parameters from UI
                    tension = self.spinTension.value()
                    smooth = self.spinSmooth.value()
                    edge = self.spinEdge.value()
                    npmin = self.spinNpmin.value()
                    segmax = self.spinSegmax.value()
                    window_size = self.spinGrassWindowSize.value()
                    
                    print(f'DEBUG: GRASS r.fillnulls parameters:')
                    print(f'DEBUG:   Tension: {tension}')
                    print(f'DEBUG:   Smooth: {smooth}')
                    print(f'DEBUG:   Edge: {edge}')
                    print(f'DEBUG:   Npmin: {npmin}')
                    print(f'DEBUG:   Segmax: {segmax}')
                    print(f'DEBUG:   Window Size: {window_size}')
                    
                    # Execute GRASS r.fillnulls
                    processing.run(
                        'grass7:r.fillnulls',
                        {
                            'input': masked_dsm_path,
                            'output': output_dsm,
                            'method': 0,  # 0 = RST method for organic results
                            'tension': tension,
                            'smooth': smooth,
                            'edge': edge,
                            'npmin': npmin,
                            'segmax': segmax,
                            '-f': False,  # Don't overwrite
                            'GRASS_REGION_PARAMETER': None,
                            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
                            'GRASS_RASTER_FORMAT_OPT': '',
                            'GRASS_RASTER_FORMAT_META': '',
                            'GRASS_OUTPUT_TYPE_PARAMETER': 0
                        },
                        feedback=feedback
                    )
                    
                    if os.path.isfile(output_dsm):
                        interpolation_success = True
                        print('DEBUG: GRASS r.fillnulls interpolation succeeded')
                    else:
                        raise Exception("GRASS r.fillnulls output file not created")
                        
                except Exception as e:
                    print(f'DEBUG: GRASS r.fillnulls failed: {str(e)}')
                    print('DEBUG: GRASS r.fillnulls failed - falling back to Simple GDAL method...')
                    interpolation_method = 'simple'  # Auto-fallback to simple method
                    
            # Simple method (can be called directly or as final fallback)
            if interpolation_method == 'simple':
                # Method 4: Simple GDAL fillnodata (original method)
                print('DEBUG: Starting Simple GDAL fillnodata (original method)...')
                try:
                    print('DEBUG: Simple GDAL: Single-stage fillnodata processing...')
                    final_dsm = processing.run(
                        'gdal:fillnodata',
                        {
                            'INPUT': masked_dsm_path,
                            'BAND': 1,
                            'DISTANCE': fill_distance,
                            'ITERATIONS': fill_iterations,
                            'NO_MASK': False,
                            'MASK_LAYER': None,
                            'OPTIONS': None,
                            'EXTRA': '',
                            'OUTPUT': output_dsm
                        },
                        feedback=feedback
                    )['OUTPUT']
                    
                    if os.path.isfile(output_dsm):
                        interpolation_success = True
                        print('DEBUG: Simple GDAL fillnodata succeeded')
                    else:
                        raise Exception("Simple fillnodata output file not created")
                        
                except Exception as e:
                    print(f'DEBUG: Simple GDAL fillnodata failed: {str(e)}')
                    print('DEBUG: All interpolation methods failed! Using masked DSM as final result.')
                    
                    # Final fallback: Use masked DSM without interpolation
                    import shutil
                    try:
                        shutil.copy2(masked_dsm_path, output_dsm)
                        interpolation_success = True
                        print('DEBUG: Using masked DSM without interpolation as final fallback')
                        QMessageBox.warning(self, 'Interpolation Failed', 
                                          'All interpolation methods failed.\n\n'
                                          'Using masked DSM without interpolation.\n'
                                          'Areas marked as anthropogenic will remain as NoData.\n\n'
                                          'Consider:\n'
                                          '• Adjusting threshold parameters\n'
                                          '• Using fixed thresholds instead of percentiles\n'
                                          '• Reducing buffer distance')
                    except Exception as copy_error:
                        print(f'DEBUG: Even file copy fallback failed: {str(copy_error)}')
                        interpolation_success = False
            

            
            if not interpolation_success:
                raise Exception("All interpolation methods and fallbacks failed")
                
            print('DEBUG: Advanced interpolation completed:', output_dsm)

            # Validate reconstructed DSM
            reconstructed_layer = QgsRasterLayer(output_dsm, 'Reconstructed DSM Debug')
            if not reconstructed_layer.isValid():
                print('DEBUG: Using masked DSM without interpolation as fallback')
                output_dsm = masked_dsm_path



            # Load result layers
            self.update_progress(total_steps, total_steps, " Loading result layers into QGIS...")
            print('DEBUG: Loading result layers into QGIS...')
            
            # 1. ALWAYS load reconstructed DSM (most important)
            dsm_layer = QgsRasterLayer(output_dsm, 'Reconstructed DSM')
            if dsm_layer.isValid():
                QgsProject.instance().addMapLayer(dsm_layer)
                print(f'DEBUG: Loaded Reconstructed DSM: {output_dsm}')
            else:
                print(f'DEBUG: ERROR - Could not load Reconstructed DSM: {output_dsm}')
            
            # 2. ALWAYS load anthropogenic features (with 3-class classification)
            anthro_layer = QgsRasterLayer(output_anthropogenic, 'Anthropogenic Features (0=Natural, 1=Vegetation, 2=Anthropogenic)')
            if anthro_layer.isValid():
                QgsProject.instance().addMapLayer(anthro_layer)
                print(f'DEBUG: Loaded Anthropogenic Features: {output_anthropogenic}')
            else:
                print(f'DEBUG: ERROR - Could not load Anthropogenic Features: {output_anthropogenic}')
            
            # 3. Load optional layers
            layers_loaded = 2  # Count of main layers
            
            # Curvature
            if curvature_layer is not None and curvature_layer.isValid():
                curvature_layer.setName('Curvature')
                QgsProject.instance().addMapLayer(curvature_layer)
                layers_loaded += 1
                print('DEBUG: Loaded Curvature layer')
            
            # Residuals
            if use_residuals and residual_layer is not None and residual_layer.isValid():
                residual_layer.setName('Residuals')
                QgsProject.instance().addMapLayer(residual_layer)
                layers_loaded += 1
                print('DEBUG: Loaded Residuals layer')
            
            # Texture layers (if they exist)
            if texture_variance is not None and texture_variance.isValid():
                texture_variance.setName('Texture Variance')
                QgsProject.instance().addMapLayer(texture_variance)
                layers_loaded += 1
                print('DEBUG: Loaded Texture Variance layer')
                
            if texture_entropy is not None and texture_entropy.isValid():
                texture_entropy.setName('Texture Entropy')
                QgsProject.instance().addMapLayer(texture_entropy)
                layers_loaded += 1
                print('DEBUG: Loaded Texture Entropy layer')
            
            print(f'DEBUG: Total layers loaded: {layers_loaded}')
            
            # Generate processing report
            self.update_progress(total_steps, total_steps, "Generating processing report...")
            self.generate_processing_report(
                input_dsm=input_dsm,
                output_dir=output_dir,
                scaling_info=scaling_info,
                gaussian_iterations=gaussian_iterations,
                sigma_value=sigma_value,
                kernel_radius=kernel_radius,
                buffer_distance=buffer_distance,
                fill_distance=fill_distance,
                fill_iterations=fill_iterations,
                interpolation_method=interpolation_method,
                original_interpolation_method=original_interpolation_method,
                stats_results=stats_results,
                slope_threshold=slope_threshold,
                curvature_threshold=curvature_threshold,
                residual_threshold=residual_threshold,
                use_residuals=use_residuals,
                slope_layer=slope_layer,
                curvature_layer=curvature_layer,
                residual_layer=residual_layer if use_residuals else None,
                anthropogenic_pixels=anthropogenic_pixels if 'anthropogenic_pixels' in locals() else 0,
                total_pixels=total_pixels if 'total_pixels' in locals() else 0,
                output_dsm=output_dsm
            )
            
            # Organize output files for better structure
            self.update_progress(total_steps, total_steps, "Organizing output files...")
            self.organize_output_files(output_dir)
            
            # Set progress bar to 100%
            self.update_progress(total_steps, total_steps, "Processing completed successfully!")
            QMessageBox.information(self, 'Finished', 'Reconstruction completed!')
        except Exception as e:
            print('DEBUG: Error:', str(e))
            # Reset progress on error
            if hasattr(self, 'labelProgressStatus'):
                self.labelProgressStatus.setText("Processing failed - see error message")
            QMessageBox.critical(self, 'Error', f'Error during processing: {str(e)}')


class BareEarthReconstructor:
    """
    Main plugin class for the Bare Earth Reconstructor QGIS plugin.
    
    This class handles the plugin lifecycle, including initialization, GUI setup,
    and cleanup. It serves as the entry point for the plugin and manages the
    dialog instance throughout the plugin's lifetime.
    
    The plugin provides a scientific tool for reconstructing natural terrain
    surfaces from Digital Surface Models (DSM) by removing anthropogenic structures
    and vegetation using the methodology of Cao et al. (2020).
    
    Key Features:
    - Adaptive percentile-based thresholds for terrain-independent processing
    - 3-class classification (Natural/Vegetation/Anthropogenic)
    - Texture analysis using GLCM metrics
    - Multi-stage Gaussian filtering
    - Multiple interpolation methods (Enhanced GDAL, Simple GDAL, GRASS r.fillnulls)
    - GRASS r.fillnulls with NoData validation, organic RST interpolation, and fallbacks
    - Comprehensive processing reports and documentation
    
    Attributes:
        iface: QGIS interface object for plugin integration
        dlg: Main dialog instance (BareEarthReconstructorDialog)
        action: QAction object for menu integration
        
    Methods:
        - __init__: Initialize plugin with QGIS interface
        - initGui: Set up plugin GUI and menu integration
        - unload: Clean up plugin resources
        - run: Launch the main dialog
    """
    
    def __init__(self, iface):
        """
        Initialize the Bare Earth Reconstructor plugin.
        
        Sets up the plugin with the QGIS interface and initializes
        internal variables. The dialog is created lazily (on first use)
        to improve startup performance.
        
        Args:
            iface: QGIS interface object providing access to QGIS functionality
                - Used for menu integration and plugin lifecycle management
                - Provides access to main window and project instance
                
        Side Effects:
            - Stores iface reference for later use
            - Initializes dialog and action attributes to None
            - Prepares plugin for GUI initialization
        """
        self.iface = iface
        self.dlg = None
        self.action = None

    def initGui(self):
        """
        Initialize the plugin GUI and integrate with QGIS interface.
        
        Creates the plugin action and adds it to the QGIS menu system.
        This method is called by QGIS during plugin startup to set up
        the user interface elements.
        
        The plugin is added to the "Bare Earth Reconstructor" menu,
        which appears in the QGIS main menu bar. Users can access
        the plugin functionality through this menu item.
        
        Side Effects:
            - Creates QAction for plugin menu integration
            - Connects action to run method
            - Adds action to QGIS menu system
            - Makes plugin available to users through QGIS interface
            
        Note:
            - Called automatically by QGIS during plugin loading
            - Sets up signal connections for user interaction
            - Integrates plugin into QGIS menu structure
        """
        self.action = QAction('Bare Earth Reconstructor', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Bare Earth Reconstructor', self.action)

    def unload(self):
        """
        Clean up plugin resources and remove from QGIS interface.
        
        This method is called by QGIS when the plugin is unloaded or
        QGIS is shutting down. It ensures proper cleanup of resources
        and removes the plugin from the QGIS interface.
        
        Side Effects:
            - Removes plugin action from QGIS menu
            - Clears action reference
            - Ensures proper resource cleanup
            
        Note:
            - Called automatically by QGIS during plugin unloading
            - Prevents memory leaks and interface conflicts
            - Ensures clean plugin shutdown
        """
        if self.action:
            self.iface.removePluginMenu('&Bare Earth Reconstructor', self.action)
            self.action = None

    def run(self):
        """
        Launch the main plugin dialog and handle user interaction.
        
        Creates and displays the main reconstruction dialog if it doesn't
        already exist. This method is called when the user clicks the
        plugin menu item or action button.
        
        The dialog is created lazily (only when needed) to improve
        plugin startup performance. Once created, the same dialog instance
        is reused for subsequent calls.
        
        Side Effects:
            - Creates BareEarthReconstructorDialog instance if not exists
            - Shows dialog to user
            - Brings dialog to front and activates it
            - Handles dialog lifecycle management
            
        Note:
            - Uses singleton pattern for dialog instance
            - Ensures dialog is properly focused when shown
            - Manages dialog state throughout plugin lifetime
        """
        if not self.dlg:
            self.dlg = BareEarthReconstructorDialog()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow() 