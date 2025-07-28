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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.populate_layers()
        self.buttonRun.clicked.connect(self.run_reconstruction)
        self.buttonBrowseDSM.clicked.connect(self.browse_dsm)
        self.buttonBrowseOutputDir.clicked.connect(self.browse_output_dir)
        
        # Connect radio button signals for threshold method switching
        self.radioPercentile.toggled.connect(self.on_threshold_method_changed)
        self.radioFixed.toggled.connect(self.on_threshold_method_changed)
        
        # Connect tab change event to update help text
        self.tabWidget.currentChanged.connect(self.update_help_text_for_tab)
        
        # Initialize UI state (Percentile mode is default)
        self.on_threshold_method_changed()
        
        # Set initial help text for first tab
        self.update_help_text_for_tab(0)

    def on_threshold_method_changed(self):
        """Handle switching between percentile and fixed threshold modes"""
        if self.radioPercentile.isChecked():
            # Enable percentile group, disable fixed group
            self.groupPercentiles.setEnabled(True)
            self.groupFixedThresholds.setEnabled(False)
            print('DEBUG: Switched to Percentile-based thresholds (Cao et al. 2020)')
        else:
            # Enable fixed group, disable percentile group
            self.groupPercentiles.setEnabled(False)
            self.groupFixedThresholds.setEnabled(True)
            print('DEBUG: Switched to Fixed thresholds')

    def populate_layers(self):
        self.comboInputDSM.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self.comboInputDSM.addItem(layer.name(), layer.id())

    def setup_help_text(self):
        """Setup help text for parameter explanations - now replaced by dynamic tab-specific help"""
        # This method is kept for compatibility but will be replaced by update_help_text_for_tab
        self.update_help_text_for_tab(0)

    def update_help_text_for_tab(self, tab_index):
        """Update help text based on currently active tab"""
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
        """Help text for Tab 1: Input & Processing"""
        return """
<b>📁 INPUT & PROCESSING</b>

<b>🗂️ Input DSM:</b>
Select your high-resolution DSM file or layer. Resolution will be detected automatically and parameters will be auto-scaled.

<b>📂 Output Directory:</b>
Choose folder for results and intermediate files. All processing outputs will be saved here.

<b>🎯 Threshold Method:</b>
<u>Percentile-based (Recommended):</u>
• Adaptive thresholds based on data distribution
• Automatically adapts to terrain type
• Mountain areas: Higher natural slopes
• Flat areas: Lower natural slopes

<u>Fixed Thresholds (Legacy):</u>
• Manual threshold values
• Same values for all terrain types
• Use for comparison or specific requirements

<b>📊 Percentile Settings:</b>
• <b>Slope:</b> % of values below anthropogenic threshold (90% = top 10% steepest)
• <b>Curvature:</b> % of values below feature threshold (95% = top 5% most curved)  
• <b>Residual:</b> % of values below anomaly threshold (95% = top 5% height differences)
• <b>Texture Variance:</b> % of values below vegetation threshold (90% = top 10% most variable)
• <b>Texture Entropy:</b> % of values below vegetation threshold (90% = top 10% most heterogeneous)

<b>📏 Fixed Threshold Values:</b>
• <b>Slope:</b> Maximum natural slope (degrees)
• <b>Curvature:</b> Maximum natural curvature
• <b>Residual:</b> Height difference threshold (meters)

<b>🔬 Scientific Method (Cao et al. 2020):</b>
Objective, reproducible, landscape-independent methodology for bare earth reconstruction.
        """

    def get_tab2_help_text(self):
        """Help text for Tab 2: Advanced Options"""
        return """
<b>⚙️ ADVANCED OPTIONS</b>

<b>🌊 Gaussian Filter:</b>
Smooths the DSM to separate terrain from features.
• <b>Sigma:</b> Smoothing strength (auto-scaled by pixel size)
• <b>Kernel Radius:</b> Filter size in pixels
• <b>Iterations:</b> Number of filter passes (2-3 recommended)

<b>🌿 Texture Analysis (3-Class):</b>
Distinguishes vegetation from anthropogenic features using surface texture patterns.
• <b>Enable:</b> Activates 3-class classification (Natural/Vegetation/Anthropogenic)
• <b>Window Size:</b> Analysis window (3x3 to 9x9 pixels)
• <b>Variance Threshold:</b> Vegetation detection sensitivity
• <b>Entropy Threshold:</b> Texture complexity threshold

<b>🎯 Filter Options:</b>
Choose which features to mask/remove:
• <b>🏠 Anthropogenic:</b> Buildings, roads, infrastructure
• <b>🌲 Vegetation:</b> Trees, bushes, forest cover

<u>Common Combinations:</u>
• Anthropogenic only: Traditional bare earth
• Vegetation only: Keep buildings, remove forest
• Both: Aggressive filtering for geology
• Neither: Validation/debugging mode

<b>🔵 Buffer & Fill:</b>
• <b>Buffer Distance:</b> Expand masked areas (meters)
• <b>Fill Distance:</b> Maximum interpolation reach (pixels)
• <b>Fill Iterations:</b> Interpolation passes (1-10)
        """

    def get_tab3_help_text(self):
        """Help text for Tab 3: Interpolation & Output"""
        return """
<b>🎨 INTERPOLATION & OUTPUT</b>

<b>🔧 Interpolation Methods:</b>
Choose algorithm for reconstructing masked areas:

<b>🌊 TPS (Thin Plate Spline):</b>
• Most organic, mathematically smooth surfaces
• Best for geological continuity
• Excellent for natural terrain reconstruction
• Slower processing, highest quality

<b>🎯 IDW (Inverse Distance Weighting):</b>
• Smooth transitions, preserves local patterns
• Morphological post-processing included
• Good balance of speed and quality
• Reliable for most applications

<b>⚡ Enhanced GDAL:</b>
• Multi-stage processing with smoothing
• Balanced speed and quality
• Reduces interpolation artifacts
• Good general-purpose choice

<b>🚀 Simple GDAL:</b>
• Fastest processing
• Basic interpolation algorithm
• May create angular artifacts
• Good for quick previews

<b>📐 Fill Parameters:</b>
• <b>Fill Distance:</b> How far to interpolate (pixels)
• <b>Fill Iterations:</b> Multiple passes for better results

<b>🎯 Quality Tips:</b>
• Use TPS for final high-quality results
• Use Enhanced/Simple for testing parameters
• Larger fill distances = smoother results
• Multiple iterations = better gap filling

<b>▶️ Processing:</b>
Click "Run Reconstruction" to start processing with current settings.
        """

    def update_progress(self, step, total_steps, message="Processing..."):
        """
        Update both progress bar and status label
        
        Args:
            step: Current step (0-based or 1-based)
            total_steps: Total number of steps
            message: Status message to display
        """
        try:
            # Update progress bar
            self.progressBar.setValue(int(step))
            self.progressBar.setMaximum(int(total_steps))
            
            # Update status label
            if hasattr(self, 'labelProgressStatus'):
                percentage = int((step / total_steps) * 100) if total_steps > 0 else 0
                status_text = f"📊 Step {step}/{total_steps} ({percentage}%) • {message}"
                self.labelProgressStatus.setText(status_text)
            
            # Force GUI update
            from qgis.PyQt.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            
        except Exception as e:
            print(f'DEBUG: Error updating progress: {str(e)}')

    def reset_progress(self):
        """Reset progress bar and status to initial state"""
        try:
            self.progressBar.setValue(0)
            self.progressBar.setMaximum(100)
            if hasattr(self, 'labelProgressStatus'):
                self.labelProgressStatus.setText("Ready to start processing...")
        except Exception as e:
            print(f'DEBUG: Error resetting progress: {str(e)}')

    def browse_dsm(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select DSM', '', 'Raster data (*.tif *.tiff *.asc *.img *.vrt *.sdat *.nc *.grd *.bil *.hdr *.adf *.dem *.dt0 *.dt1 *.dt2 *.flt *.hgt *.raw *.xyz *.txt);;All files (*)')
        if file_path:
            self.lineEditInputDSM.setText(file_path)

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select output directory', '')
        if dir_path:
            self.lineEditOutputDir.setText(dir_path)

    def get_input_dsm(self):
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
        Get pixel size from DSM and auto-scale parameters based on resolution
        Returns scaled parameters optimized for the detected resolution
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
        Calculate percentile value for a raster layer using memory-efficient processing
        Based on Cao et al. (2020) methodology for adaptive thresholds
        
        Args:
            raster_layer: QgsRasterLayer to analyze
            percentile: Percentile value (0-100)
            
        Returns:
            float: Percentile value or None if calculation failed
        """
        try:
            print(f'DEBUG: Calculating {percentile}th percentile for {raster_layer.name()}...')
            
            # Get raster provider
            provider = raster_layer.dataProvider()
            if not provider.isValid():
                raise Exception(f"Invalid raster provider for {raster_layer.name()}")
            
            # Get raster dimensions
            width = raster_layer.width()
            height = raster_layer.height()
            extent = raster_layer.extent()
            
            print(f'DEBUG: Raster dimensions: {width}x{height} pixels')
            
            # For very large rasters, use sampling to improve performance
            if width * height > 10000000:  # > 10M pixels
                print('DEBUG: Large raster detected, using sampling for percentile calculation')
                sample_factor = 10  # Every 10th pixel
                
                # Create sample coordinates
                x_coords = []
                y_coords = []
                for i in range(0, width, sample_factor):
                    for j in range(0, height, sample_factor):
                        x_coords.append(extent.xMinimum() + (i + 0.5) * raster_layer.rasterUnitsPerPixelX())
                        y_coords.append(extent.yMaximum() - (j + 0.5) * raster_layer.rasterUnitsPerPixelY())
                
                # Sample raster values
                values = []
                for x, y in zip(x_coords, y_coords):
                    value, success = provider.sample(QgsPointXY(x, y), 1)
                    if success and value != provider.sourceNoDataValue(1):
                        values.append(value)
                        
                print(f'DEBUG: Sampled {len(values)} valid pixels from {len(x_coords)} total samples')
                
            else:
                print('DEBUG: Reading complete raster for percentile calculation')
                
                # Read entire raster band
                block = provider.block(1, extent, width, height)
                if not block.isValid():
                    raise Exception("Could not read raster block")
                
                # Extract valid values (exclude NoData)
                values = []
                nodata_value = provider.sourceNoDataValue(1)
                
                for i in range(width):
                    for j in range(height):
                        value = block.value(i, j)
                        if value != nodata_value and not (value != value):  # Check for NaN
                            values.append(value)
                
                print(f'DEBUG: Extracted {len(values)} valid pixels from {width*height} total pixels')
            
            if len(values) == 0:
                raise Exception("No valid pixel values found")
            
            # Calculate percentile using numpy for efficiency
            import numpy as np
            values_array = np.array(values)
            
            # Calculate percentile
            percentile_value = np.percentile(values_array, percentile)
            
            # Calculate some additional statistics for debugging
            min_val = np.min(values_array)
            max_val = np.max(values_array)
            mean_val = np.mean(values_array)
            std_val = np.std(values_array)
            
            print(f'DEBUG: Raster statistics - Min: {min_val:.4f}, Max: {max_val:.4f}')
            print(f'DEBUG: Raster statistics - Mean: {mean_val:.4f}, StdDev: {std_val:.4f}')
            print(f'DEBUG: {percentile}th percentile: {percentile_value:.4f}')
            
            return float(percentile_value)
            
        except ImportError:
            print('DEBUG: NumPy not available, using alternative percentile calculation')
            
            # Fallback: Simple percentile calculation without numpy
            if len(values) == 0:
                return None
                
            values.sort()
            index = int((percentile / 100.0) * (len(values) - 1))
            percentile_value = values[index]
            
            print(f'DEBUG: {percentile}th percentile (fallback): {percentile_value:.4f}')
            return float(percentile_value)
            
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
        Generate a comprehensive processing report documenting all parameters and results
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
                            # Use histogram for efficient class counting
                            provider = anthro_layer.dataProvider()
                            width = anthro_layer.width()
                            height = anthro_layer.height()
                            extent = anthro_layer.extent()
                            
                            # Read entire raster to count classes
                            block = provider.block(1, extent, width, height)
                            class_counts = {0: 0, 1: 0, 2: 0}  # Natural, Vegetation, Anthropogenic
                            total_pixels = 0
                            
                            for i in range(width):
                                for j in range(height):
                                    value = block.value(i, j)
                                    if value == value:  # Check not NaN
                                        class_counts[int(value)] = class_counts.get(int(value), 0) + 1
                                        total_pixels += 1
                            
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
        Organize output files after processing completion:
        - Keep main results in root directory
        - Move intermediate files to 'Intermediate' subdirectory
        """
        try:
            import os
            import shutil
            from datetime import datetime
            
            print('DEBUG: 🗂️ Organizing output files for better structure...')
            
            # Create intermediate files directory
            intermediate_dir = os.path.join(output_dir, 'Intermediate')
            os.makedirs(intermediate_dir, exist_ok=True)
            
            # Define final result files (keep in main directory)
            final_files = [
                'reconstructed_dsm.tif',           # 🎯 Main result
                'anthropogenic_features.tif',      # 🎯 Main classification
                'texture_variance*.tif',           # 🎯 Texture analysis results
                'texture_entropy*.tif',            # 🎯 Texture analysis results
                'reconstruction_report_*.txt'      # 📊 Report (handled separately with wildcard)
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
                            print(f'DEBUG: ✅ Final pattern match: {filename} matches {final_pattern}')
                            break
                    elif filename == final_pattern:
                        should_keep = True
                        break
                
                if should_keep:
                    print(f'DEBUG: ✅ Keeping in main directory: {filename}')
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
                            print(f'DEBUG: 📦 Pattern match: {filename} matches {intermediate_pattern}')
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
                        print(f'DEBUG: 📦 Moved to Intermediate/: {filename}')
                        moved_count += 1
                    except Exception as e:
                        # File is likely locked by QGIS - keep in main directory with note
                        print(f'DEBUG: 🔒 File locked, keeping in main: {filename} ({str(e)[:50]}...)')
                        kept_count += 1
                else:
                    # Unknown file - keep in main directory but log it
                    print(f'DEBUG: ❓ Unknown file kept in main: {filename}')
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
                    
                print(f'DEBUG: 📋 Organization summary created: _file_organization_summary.txt')
            except Exception as e:
                print(f'DEBUG: Error creating organization summary: {str(e)}')
            
            print(f'DEBUG: ✅ File organization completed!')
            print(f'DEBUG: 📁 Main directory: {kept_count} files (final results)')
            print(f'DEBUG: 📦 Intermediate/: {moved_count} files (intermediate results)')
            
            # Show user notification
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                # Simple check if there were any locked files (based on kept vs moved ratio)
                locked_files_note = ""
                if kept_count > 5:  # If more than 5 files kept, likely some were locked
                    locked_files_note = f"\n\n🔒 Note: Some files may have remained in main directory\nbecause they were locked by QGIS."
                
                QMessageBox.information(
                    self, 
                    'Files Organized', 
                    f'📁 Output files organized successfully!\n\n'
                    f'✅ Main Results: {kept_count} files\n'
                    f'📦 Intermediate/: {moved_count} files\n\n'
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
        Comprehensive statistical analysis of geomorphometric parameters
        Following Cao et al. (2020) methodology
        
        Args:
            slope_layer: QgsRasterLayer with slope values
            curvature_layer: QgsRasterLayer with curvature values  
            residual_layer: QgsRasterLayer with residual values (optional)
            texture_variance: QgsRasterLayer with texture variance (optional)
            texture_entropy: QgsRasterLayer with texture entropy (optional)
            
        Returns:
            dict: Statistical analysis results
        """
        try:
            print('DEBUG: ===== Geomorphometric Statistical Analysis =====')
            print('DEBUG: Following Cao et al. (2020) methodology')
            
            # Get percentile values from UI
            slope_percentile = self.spinSlopePercentile.value()
            curvature_percentile = self.spinCurvaturePercentile.value()
            residual_percentile = self.spinResidualPercentile.value()
            variance_percentile = self.spinVariancePercentile.value()
            entropy_percentile = self.spinEntropyPercentile.value()
            
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

            # Calculate texture thresholds if available OR use default values from UI
            variance_threshold = None
            entropy_threshold = None
            use_texture = False
            
            if texture_variance is not None and texture_entropy is not None:
                print('DEBUG: Calculating texture percentiles for vegetation detection...')
                variance_threshold = self.calculate_raster_percentiles(texture_variance, variance_percentile)
                entropy_threshold = self.calculate_raster_percentiles(texture_entropy, entropy_percentile)
                use_texture = True
                print(f'DEBUG: Variance {variance_percentile}th percentile: {variance_threshold:.4f}')
                print(f'DEBUG: Entropy {entropy_percentile}th percentile: {entropy_threshold:.4f}')
            else:
                # Use default values from UI if texture analysis failed
                print('DEBUG: Texture analysis failed/disabled, using default values from UI...')
                try:
                    variance_threshold = self.spinVarianceThreshold.value()
                    entropy_threshold = self.spinEntropyThreshold.value()
                    # Check if texture analysis is enabled in UI
                    if hasattr(self, 'checkTextureAnalysis') and self.checkTextureAnalysis.isChecked():
                        use_texture = True
                        print(f'DEBUG: Using default variance threshold: {variance_threshold:.4f}')
                        print(f'DEBUG: Using default entropy threshold: {entropy_threshold:.4f}')
                        print('DEBUG: Texture analysis enabled with default values (will use 3-class classification)')
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
                'use_texture': use_texture
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
                print(f'DEBUG: Variance threshold ({variance_percentile}th percentile): {variance_threshold:.4f}')
                print(f'DEBUG: Entropy threshold ({entropy_percentile}th percentile): {entropy_threshold:.4f}')
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
        Perform texture analysis using GRASS r.texture to distinguish vegetation from anthropogenic features
        Based on Gray-Level Co-Occurrence Matrix (GLCM) metrics
        
        Args:
            input_raster_path: Path to filtered DSM
            output_dir: Output directory
            feedback: Processing feedback
            
        Returns:
            tuple: (variance_layer, entropy_layer) or (None, None) if disabled/failed
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
        Alternative texture calculation using GDAL focal statistics
        This provides a reasonable approximation of variance and entropy
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
            self.update_progress(0, total_steps, "🚀 Starting DSM processing...")

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
                    self.update_progress(iteration + 1, total_steps, f"🌊 Gaussian Filter - Iteration {iteration + 1}/{gaussian_iterations}")
                    
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
            self.update_progress(gaussian_iterations + 1, total_steps, "📏 Calculating residuals (Original - Filtered DSM)...")
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
            self.update_progress(gaussian_iterations + 2, total_steps, "⛰️ Calculating slope analysis...")
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
            self.update_progress(gaussian_iterations + 3, total_steps, "🌀 Calculating curvature analysis...")
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
            self.update_progress(gaussian_iterations + 4, total_steps, "🌿 Performing texture analysis (3-class classification)...")
            texture_variance, texture_entropy = self.perform_texture_analysis(filtered_dsm_path, output_dir, feedback)

            # Step 5a: Statistical Analysis and Adaptive Threshold Calculation (Cao et al. 2020)
            self.update_progress(gaussian_iterations + 5, total_steps, "📊 Statistical analysis & adaptive thresholds (Cao et al. 2020)...")
            print('DEBUG: Starting statistical analysis for adaptive thresholds...')
            
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
                    print('DEBUG: Using fixed threshold fallback values')
                else:
                    # Use calculated percentile thresholds
                    slope_threshold = stats_results['slope_threshold']
                    curvature_pos_threshold = stats_results['curvature_pos_threshold']
                    curvature_neg_threshold = stats_results['curvature_neg_threshold']
                    residual_threshold = stats_results['residual_threshold']
                    
                    # For backwards compatibility with existing logic, use symmetric curvature threshold
                    curvature_threshold = max(abs(curvature_pos_threshold), abs(curvature_neg_threshold))
                    
                    print('DEBUG: ===== Applied Adaptive Thresholds =====')
                    print(f'DEBUG: Slope threshold: {slope_threshold:.4f}°')
                    print(f'DEBUG: Curvature threshold: ±{curvature_threshold:.4f}')
                    if residual_threshold is not None:
                        print(f'DEBUG: Residual threshold: ±{residual_threshold:.4f}m')
                    print('DEBUG: ========================================')
                    
            else:
                print('DEBUG: Using fixed thresholds (legacy mode)')
                slope_threshold = self.spinSlope.value()
                curvature_threshold = self.spinCurvature.value()
                residual_threshold = self.spinResidual.value()
                
                print('DEBUG: ===== Applied Fixed Thresholds =====')
                print(f'DEBUG: Slope threshold: {slope_threshold:.4f}°')
                print(f'DEBUG: Curvature threshold: ±{curvature_threshold:.4f}')
                print(f'DEBUG: Residual threshold: ±{residual_threshold:.4f}m')
                print('DEBUG: ====================================')

            # Step 5: Identify anthropogenic features
            self.update_progress(gaussian_iterations + 6, total_steps, "🏠 Identifying anthropogenic features...")
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
                    calc_expression = f'if(("variance@1" > {variance_threshold} OR "entropy@1" > {entropy_threshold}), 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold} OR ("residual@1" > {residual_threshold} OR "residual@1" < -{residual_threshold})) AND ("variance@1" <= {variance_threshold}), 2, 0))'
                else:
                    calc_expression = f'if(("variance@1" > {variance_threshold} OR "entropy@1" > {entropy_threshold}), 1, if(("slope@1" > {slope_threshold} OR "curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold}) AND ("variance@1" <= {variance_threshold}), 2, 0))'
                
                print(f'DEBUG: 🔍 CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG: 🔍 Thresholds - Variance: {variance_threshold}, Entropy: {entropy_threshold}')
                print(f'DEBUG: 🔍 Thresholds - Slope: {slope_threshold}, Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG: 🔍 Thresholds - Residual: ±{residual_threshold}')
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
                
                print(f'DEBUG: 🔍 CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG: 🔍 Thresholds - Vegetation slope: {vegetation_slope_threshold}, Anthropogenic slope: {slope_threshold}')
                print(f'DEBUG: 🔍 Thresholds - Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG: 🔍 Thresholds - Residual: ±{residual_threshold}')
            else:
                # Original binary classification (anthropogenic=1, natural=0)
                print('DEBUG: Using binary classification (no texture)')
                if use_residuals and residual_layer is not None:
                    calc_expression = f'("slope@1" > {slope_threshold}) OR ("curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold}) OR ("residual@1" > {residual_threshold} OR "residual@1" < -{residual_threshold})'
                else:
                    calc_expression = f'("slope@1" > {slope_threshold}) OR ("curvature@1" > {curvature_threshold} OR "curvature@1" < -{curvature_threshold})'
                
                print(f'DEBUG: 🔍 CLASSIFICATION FORMULA: {calc_expression}')
                print(f'DEBUG: 🔍 Thresholds - Slope: {slope_threshold}, Curvature: ±{curvature_threshold}')
                if use_residuals and residual_layer is not None:
                    print(f'DEBUG: 🔍 Thresholds - Residual: ±{residual_threshold}')
            
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
            
            # 🔍 DEBUGGING: Check classification result immediately
            print('DEBUG: 🔍 CHECKING CLASSIFICATION RESULT...')
            classification_layer = QgsRasterLayer(output_anthropogenic, 'Classification_Check')
            if classification_layer.isValid():
                classification_provider = classification_layer.dataProvider()
                classification_stats = classification_provider.bandStatistics(1, QgsRasterBandStats.All)
                print(f'DEBUG: 🔍 Classification result - Min: {classification_stats.minimumValue}, Max: {classification_stats.maximumValue}')
                print(f'DEBUG: 🔍 Classification result - Mean: {classification_stats.mean:.3f}, StdDev: {classification_stats.stdDev:.3f}')
                
                # Sample values to see what classes were actually produced
                try:
                    block = classification_provider.block(1, classification_layer.extent(), 200, 200)  # Larger sample
                    unique_values = set()
                    class_counts = {0: 0, 1: 0, 2: 0}
                    for i in range(min(200, block.width())):
                        for j in range(min(200, block.height())):
                            value = block.value(i, j)
                            if value != block.noDataValue():
                                int_value = int(value)
                                unique_values.add(int_value)
                                if int_value in class_counts:
                                    class_counts[int_value] += 1
                    
                    print(f'DEBUG: 🔍 Unique classification values: {sorted(unique_values)}')
                    print(f'DEBUG: 🔍 Class distribution in sample:')
                    for class_id, count in class_counts.items():
                        percentage = (count / sum(class_counts.values())) * 100 if sum(class_counts.values()) > 0 else 0
                        print(f'DEBUG: 🔍   Class {class_id}: {count} pixels ({percentage:.1f}%)')
                    
                    if 2 not in unique_values:
                        print('DEBUG: ❌ CRITICAL: Class 2 (Anthropogenic) was NOT produced!')
                        print('DEBUG: 🔍 This explains why filtering fails - no class 2 pixels exist!')
                    else:
                        print('DEBUG: ✅ Class 2 (Anthropogenic) was produced successfully')
                        
                except Exception as e:
                    print(f'DEBUG: ⚠️ Could not sample classification values: {str(e)}')
            else:
                print('DEBUG: ❌ ERROR: Classification result layer is invalid!')
            
            # Calculate anthropogenic statistics
            test_layer = QgsRasterLayer(output_anthropogenic, 'Test')
            if test_layer.isValid():
                # 🔍 CRITICAL DEBUGGING: Check actual raster values
                print('DEBUG: 🔍 ANALYZING ANTHROPOGENIC FEATURES RASTER...')
                provider = test_layer.dataProvider()
                stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                print(f'DEBUG: 🔍 Anthropogenic raster - Min: {stats.minimumValue}, Max: {stats.maximumValue}')
                print(f'DEBUG: 🔍 Anthropogenic raster - Mean: {stats.mean:.3f}, StdDev: {stats.stdDev:.3f}')
                
                # Sample some values to see what's actually in the raster
                try:
                    block = provider.block(1, test_layer.extent(), 100, 100)  # Sample 100x100 pixels
                    unique_values = set()
                    for i in range(min(100, block.width())):
                        for j in range(min(100, block.height())):
                            value = block.value(i, j)
                            if value != block.noDataValue():
                                unique_values.add(int(value))
                    print(f'DEBUG: 🔍 Unique values found in sample: {sorted(unique_values)}')
                    
                    if len(unique_values) == 2 and 0 in unique_values and 1 in unique_values:
                        print('DEBUG: ❌ PROBLEM: Raster is BINARY (0,1) not 3-class (0,1,2)!')
                    elif len(unique_values) == 3 and 0 in unique_values and 1 in unique_values and 2 in unique_values:
                        print('DEBUG: ✅ Raster is 3-class (0,1,2) as expected')
                    else:
                        print(f'DEBUG: ⚠️ Unexpected values: {sorted(unique_values)}')
                except Exception as e:
                    print(f'DEBUG: ⚠️ Could not sample raster values: {str(e)}')
                
                anthropogenic_pixels = stats.sum
                total_pixels = test_layer.width() * test_layer.height()
                anthropogenic_percentage = (anthropogenic_pixels / total_pixels) * 100
                print(f'DEBUG: Anthropogenic features detected: {anthropogenic_percentage:.1f}% of area')

            # Step 6: Buffer the anthropogenic mask
            self.update_progress(gaussian_iterations + 7, total_steps, f"🔵 Buffering features ({buffer_distance:.1f}m distance)...")
            
            print(f'DEBUG: Buffer Distance from UI: {buffer_distance:.1f}m')
            
            # Handle special case: buffer_distance = 0.0 means no buffering
            if buffer_distance <= 0.0:
                print('DEBUG: Buffer distance is 0.0 - skipping buffering, using original mask')
                output_buffered = os.path.join(output_dir, 'buffered_anthropogenic.tif')
                
                if use_texture:
                    # For 3-class system: extract selected features based on filter options
                    print('DEBUG: Extracting selected features based on filter options (no buffering)')
                    
                    # Get filter options from UI
                    print('DEBUG: 🔍 CHECKING UI FILTER ELEMENTS (MASKING)...')
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
                    
                    print(f'DEBUG: 🔍 Using formula: {formula}')
                    
                    # Load the anthropogenic features raster
                    anthropogenic_layer = QgsRasterLayer(output_anthropogenic, 'Anthropogenic_For_Masking')
                    if not anthropogenic_layer.isValid():
                        raise Exception("Could not load anthropogenic features raster for masking")
                    
                    # Create raster calculator entry
                    from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
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
                    
                    # 🔍 Check the result of filtering
                    if os.path.isfile(output_buffered):
                        filtered_layer = QgsRasterLayer(output_buffered, 'Filtered_Check')
                        if filtered_layer.isValid():
                            filtered_stats = filtered_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                            print(f'DEBUG: 🔍 Filtered result - Min: {filtered_stats.minimumValue}, Max: {filtered_stats.maximumValue}')
                            print(f'DEBUG: 🔍 Filtered result - Mean: {filtered_stats.mean:.3f}, Sum: {filtered_stats.sum:.0f}')
                            
                            if filtered_stats.sum == 0:
                                print('DEBUG: ❌ CRITICAL: Filtering resulted in empty mask!')
                                print('DEBUG: 🔍 This means the formula found no matching pixels!')
                            else:
                                print(f'DEBUG: ✅ Filtering successful - {filtered_stats.sum:.0f} pixels selected')
                        else:
                            print('DEBUG: ❌ ERROR: Filtered raster is invalid!')
                    else:
                        print('DEBUG: ❌ ERROR: Filtered raster file was not created!')
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
                    print('DEBUG: 🔍 CHECKING UI FILTER ELEMENTS (MASKING)...')
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
                    
                    print(f'DEBUG: 🔍 Using formula: {formula}')
                    
                    anthropogenic_only_path = os.path.join(output_dir, 'selected_features_for_buffering.tif')
                    
                    # Create binary mask based on selected features using QGIS Raster Calculator
                    print(f'DEBUG: 🔍 Using formula: {formula}')
                    
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
                    
                    # 🔍 DEBUGGING: Check the result of initial filtering
                    print('DEBUG: 🔍 CHECKING INITIAL FILTERING RESULT...')
                    if os.path.isfile(anthropogenic_only_path):
                        initial_filter_layer = QgsRasterLayer(anthropogenic_only_path, 'Initial_Filter_Check')
                        if initial_filter_layer.isValid():
                            initial_stats = initial_filter_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                            print(f'DEBUG: 🔍 Initial filtering - Min: {initial_stats.minimumValue}, Max: {initial_stats.maximumValue}')
                            print(f'DEBUG: 🔍 Initial filtering - Mean: {initial_stats.mean:.3f}, Sum: {initial_stats.sum:.0f}')
                            
                            if initial_stats.sum == 0:
                                print('DEBUG: ❌ CRITICAL: Initial filtering resulted in empty mask!')
                                print('DEBUG: 🔍 This means the formula found no matching pixels!')
                            else:
                                print(f'DEBUG: ✅ Initial filtering successful - {initial_stats.sum:.0f} pixels selected')
                        else:
                            print('DEBUG: ❌ ERROR: Initial filtered raster is invalid!')
                    else:
                        print('DEBUG: ❌ ERROR: Initial filtered raster file was not created!')
                    
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
            
            # 🔍 DEBUGGING: Check the final buffered result
            print('DEBUG: 🔍 CHECKING FINAL BUFFERED RESULT...')
            if os.path.isfile(output_buffered):
                final_buffer_layer = QgsRasterLayer(output_buffered, 'Final_Buffer_Check')
                if final_buffer_layer.isValid():
                    final_buffer_stats = final_buffer_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                    print(f'DEBUG: 🔍 Final buffered result - Min: {final_buffer_stats.minimumValue}, Max: {final_buffer_stats.maximumValue}')
                    print(f'DEBUG: 🔍 Final buffered result - Mean: {final_buffer_stats.mean:.3f}, Sum: {final_buffer_stats.sum:.0f}')
                    
                    if final_buffer_stats.sum == 0:
                        print('DEBUG: ❌ CRITICAL: Final buffering resulted in empty mask!')
                        print('DEBUG: 🔍 This means the buffering operation failed!')
                    else:
                        print(f'DEBUG: ✅ Final buffering successful - {final_buffer_stats.sum:.0f} pixels selected')
                else:
                    print('DEBUG: ❌ ERROR: Final buffered raster is invalid!')
            else:
                print('DEBUG: ❌ ERROR: Final buffered raster file was not created!')
            
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
            self.update_progress(gaussian_iterations + 8, total_steps, "🎭 Masking DSM with detected features...")
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
                print('DEBUG: 🔍 CHECKING UI FILTER ELEMENTS (MASKING)...')
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
                
                print(f'DEBUG: 🔍 Using formula: {formula}')
                
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
                
                # 🔍 Check the result of filtering
                if os.path.isfile(output_buffered):
                    filtered_layer = QgsRasterLayer(output_buffered, 'Filtered_Check')
                    if filtered_layer.isValid():
                        filtered_stats = filtered_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
                        print(f'DEBUG: 🔍 Filtered result - Min: {filtered_stats.minimumValue}, Max: {filtered_stats.maximumValue}')
                        print(f'DEBUG: 🔍 Filtered result - Mean: {filtered_stats.mean:.3f}, Sum: {filtered_stats.sum:.0f}')
                        
                        if filtered_stats.sum == 0:
                            print('DEBUG: ❌ CRITICAL: Filtering resulted in empty mask!')
                            print('DEBUG: 🔍 This means the formula found no matching pixels!')
                        else:
                            print(f'DEBUG: ✅ Filtering successful - {filtered_stats.sum:.0f} pixels selected')
                    else:
                        print('DEBUG: ❌ ERROR: Filtered raster is invalid!')
                else:
                    print('DEBUG: ❌ ERROR: Filtered raster file was not created!')
            else:
                # Original binary masking
                calc_expression = 'if ( "buffered_mask@1" = 0, "filtered_dsm@1", 0/0 )'
                print('DEBUG: Using binary masking - masking all detected features')
            
            # 🔍 CRITICAL DEBUGGING: Comprehensive masking diagnostics
            print(f'DEBUG: 🎯 Masking expression: {calc_expression}')
            print(f'DEBUG: 🎯 DSM layer valid: {dsm_layer_for_calc.isValid()}')
            print(f'DEBUG: 🔍 Mask layer valid: {anthropogenic_layer_for_calc.isValid()}')

            # 🔍 Check mask content before applying
            try:
                if anthropogenic_layer_for_calc and anthropogenic_layer_for_calc.isValid():
                    provider = anthropogenic_layer_for_calc.dataProvider()
                    stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                    print(f'DEBUG: 🔍 Mask statistics - Min: {stats.minimumValue}, Max: {stats.maximumValue}, Mean: {stats.mean:.3f}')
                    print(f'DEBUG: 📊 Mask valid pixels: {stats.elementCount:,}')
                    
                    # Critical check: If mask is all zeros, no masking will occur!
                    if stats.maximumValue == 0:
                        print('DEBUG: ❌ CRITICAL ERROR: Mask contains only 0 values - NO MASKING WILL OCCUR!')
                        print('DEBUG: ❌ This means no anthropogenic features were detected in buffering!')
                    elif stats.minimumValue == stats.maximumValue == 1:
                        print('DEBUG: ❌ CRITICAL ERROR: Mask contains only 1 values - ENTIRE DSM WILL BE MASKED!')
                    else:
                        masked_pixels = int(stats.mean * stats.elementCount)
                        masking_percentage = (masked_pixels / stats.elementCount) * 100
                        print(f'DEBUG: ✅ Mask OK: ~{masking_percentage:.1f}% of pixels will be masked')
                        
                else:
                    print('DEBUG: ❌ CRITICAL ERROR: Mask layer is invalid!')
                    
            except Exception as mask_debug_error:
                print(f'DEBUG: ⚠️ Could not analyze mask: {str(mask_debug_error)}')
            
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

            print('DEBUG: 🔍 Starting raster calculator operation...')
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
            print(f'DEBUG: 🔍 Raster calculator result code: {result}')

            if result != QgsRasterCalculator.Success:
                print(f'DEBUG: ❌ CRITICAL ERROR: Masking operation failed with code: {result}')
                raise Exception(f"Masking operation failed with code: {result}")
            else:
                print('DEBUG: ✅ Raster calculator completed successfully')
            
            if not os.path.isfile(masked_dsm_path):
                print(f'DEBUG: ❌ CRITICAL ERROR: Masked DSM file was not created: {masked_dsm_path}')
                raise Exception(f"Masked DSM was not created: {masked_dsm_path}")
            else:
                # 🔍 CRITICAL: Validate the masked DSM
                masked_dsm_size = os.path.getsize(masked_dsm_path)
                print(f'DEBUG: ✅ Masked DSM created: {masked_dsm_size:,} bytes')
                
                # Compare with original DSM
                original_dsm_size = os.path.getsize(filtered_dsm_path)
                print(f'DEBUG: 📊 Original DSM size: {original_dsm_size:,} bytes')
                
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
                        
                        print(f'DEBUG: 🔍 Original DSM - Valid pixels: {original_stats.elementCount:,}')
                        print(f'DEBUG: 📊 Masked DSM - Valid pixels: {stats.elementCount:,}')
                        print(f'DEBUG: 🎯 MASKING RESULT: {pixels_removed:,} pixels removed ({masking_percentage:.1f}% of DSM)')
                        
                        if masking_percentage < 1.0:
                            print('DEBUG: ⚠️ WARNING: Very few pixels masked - check buffer generation!')
                        elif masking_percentage > 90.0:
                            print('DEBUG: ⚠️ WARNING: Too many pixels masked - check classification thresholds!')
                        else:
                            print('DEBUG: ✅ Reasonable masking percentage detected')
                            
                        # Test a few specific values
                        print(f'DEBUG: 📊 Masked DSM stats - Min: {stats.minimumValue:.2f}, Max: {stats.maximumValue:.2f}, Mean: {stats.mean:.2f}')
                        
                        # CRITICAL TEST: Are values actually different?
                        if abs(stats.mean - original_stats.mean) < 0.01 and pixels_removed == 0:
                            print('DEBUG: ❌ CRITICAL PROBLEM: Masked DSM appears identical to original!')
                            print('DEBUG: ❌ This suggests masking operation did not work properly!')
                        else:
                            print('DEBUG: ✅ Masked DSM is different from original - masking appears successful')
                            
                    else:
                        print('DEBUG: ❌ ERROR: Created masked DSM is invalid!')
                        
                except Exception as validation_error:
                    print(f'DEBUG: ⚠️ Masked DSM validation failed: {str(validation_error)}')

            # Step 8: Advanced Interpolation on masked DSM with selected method
            output_dsm = os.path.join(output_dir, 'reconstructed_dsm.tif')
            
            # Determine selected interpolation method from UI
            interpolation_method = 'tps'  # Default
            if self.radioTPS.isChecked():
                interpolation_method = 'tps'
            elif self.radioIDW.isChecked():
                interpolation_method = 'idw'
            elif self.radioEnhanced.isChecked():
                interpolation_method = 'enhanced'
            elif self.radioSimple.isChecked():
                interpolation_method = 'simple'
            
            # Update progress with selected method
            self.update_progress(gaussian_iterations + 9, total_steps, f"🎨 Surface reconstruction using {interpolation_method.upper()}...")
            
            # Store original method for report (before potential fallbacks change it)
            original_interpolation_method = interpolation_method
            interpolation_success = False
            
            # Apply selected interpolation method with robust fallbacks
            if interpolation_method == 'tps':
                # TPS (Thin Plate Spline) interpolation for organic surfaces
                try:
                    sample_points_path = os.path.join(output_dir, 'sample_points_for_tps.shp')
                    
                    try:
                        processing.run(
                            'gdal:pixelstopoints',
                            {
                                'INPUT_RASTER': masked_dsm_path,
                                'RASTER_BAND': 1,
                                'FIELD_NAME': 'VALUE',
                                'OUTPUT': sample_points_path
                            },
                            feedback=feedback
                        )
                        
                        from qgis.core import QgsVectorLayer
                        points_layer = QgsVectorLayer(sample_points_path, 'Sample_Points', 'ogr')
                        if points_layer.isValid() and points_layer.featureCount() > 10:
                            tps_result = processing.run(
                                'qgis:thinplatespline',
                                {
                                    'POINTS': sample_points_path,
                                    'Z_FIELD': 'VALUE',
                                    'EXTENT': dsm_layer_for_calc.extent(),
                                    'PIXEL_SIZE': scaling_info['pixel_size'],
                                    'OUTPUT': output_dsm
                                },
                                feedback=feedback
                            )
                            
                            if os.path.isfile(output_dsm):
                                interpolation_success = True
                                
                                # Apply gentle Gaussian smoothing to TPS result
                                smoothed_output = os.path.join(output_dir, 'reconstructed_dsm_smoothed.tif')
                                try:
                                    processing.run(
                                        'sagang:gaussianfilter',
                                        {
                                            'INPUT': output_dsm,
                                            'SIGMA': 0.5,  # Gentle smoothing
                                            'KERNEL_TYPE': 1,
                                            'KERNEL_RADIUS': 2,
                                            'RESULT': smoothed_output
                                        },
                                        feedback=feedback
                                    )
                                    if os.path.isfile(smoothed_output):
                                        output_dsm = smoothed_output
                                except:
                                    pass
                            else:
                                raise Exception("TPS output file not created")
                        else:
                            raise Exception("Insufficient points for TPS interpolation")
                            
                    except Exception as points_error:
                        raise Exception("Point creation failed, using fallback")
                        
                except Exception as e:
                    interpolation_method = 'enhanced'  # Auto-fallback to enhanced method
                    
            if interpolation_method == 'idw':
                # IDW (Inverse Distance Weighting) interpolation
                try:
                    sample_points_path = os.path.join(output_dir, 'sample_points_for_idw.shp')
                    
                    try:
                        processing.run(
                            'gdal:pixelstopoints',
                            {
                                'INPUT_RASTER': masked_dsm_path,
                                'RASTER_BAND': 1,
                                'FIELD_NAME': 'VALUE',
                                'OUTPUT': sample_points_path
                            },
                            feedback=feedback
                        )
                        
                        idw_result = processing.run(
                            'qgis:idwinterpolation',
                            {
                                'INTERPOLATION_DATA': f'{sample_points_path}::~::0::~::VALUE::~::0',
                                'DISTANCE_COEFFICIENT': 2.0,  # Standard IDW power
                                'EXTENT': dsm_layer_for_calc.extent(),
                                'PIXEL_SIZE': scaling_info['pixel_size'],
                                'OUTPUT': output_dsm
                            },
                            feedback=feedback
                        )
                        
                        if os.path.isfile(output_dsm):
                            interpolation_success = True
                            
                            # Apply morphological smoothing to IDW result
                            smoothed_output = os.path.join(output_dir, 'reconstructed_dsm_morpho_smoothed.tif')
                            try:
                                processing.run(
                                    'sagang:morphologicalfilter',
                                    {
                                        'INPUT': output_dsm,
                                        'KERNEL_TYPE': 1,  # Circle
                                        'KERNEL_RADIUS': 1,
                                        'METHOD': 5,  # Closing (fill gaps organically)
                                        'RESULT': smoothed_output
                                    },
                                    feedback=feedback
                                )
                                if os.path.isfile(smoothed_output):
                                    output_dsm = smoothed_output
                            except:
                                pass
                        else:
                            raise Exception("IDW output file not created")
                            
                    except Exception as points_error:
                        raise Exception("Point creation failed, using fallback")
                        
                except Exception as e:
                    interpolation_method = 'enhanced'  # Auto-fallback to enhanced method
            
            # Enhanced method (can be called directly or as fallback)        
            if interpolation_method == 'enhanced':
                # Method 3: Enhanced GDAL fillnodata with multiple iterations and smoothing
                try:
                    print('DEBUG: Trying enhanced GDAL fillnodata with multi-stage processing...')
                    
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
                    
            # Simple method (can be called directly or as final fallback)
            if interpolation_method == 'simple':
                # Method 4: Simple GDAL fillnodata (original method)
                try:
                    print('DEBUG: Using simple GDAL fillnodata (original method)...')
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
            self.update_progress(total_steps, total_steps, "🗂️ Loading result layers into QGIS...")
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
            self.update_progress(total_steps, total_steps, "📊 Generating processing report...")
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
                stats_results=stats_results if self.radioPercentile.isChecked() and 'stats_results' in locals() else None,
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
            self.update_progress(total_steps, total_steps, "🗂️ Organizing output files...")
            self.organize_output_files(output_dir)
            
            # Set progress bar to 100%
            self.update_progress(total_steps, total_steps, "✅ Processing completed successfully!")
            QMessageBox.information(self, 'Finished', 'Reconstruction completed!')
        except Exception as e:
            print('DEBUG: Error:', str(e))
            # Reset progress on error
            if hasattr(self, 'labelProgressStatus'):
                self.labelProgressStatus.setText("❌ Processing failed - see error message")
            QMessageBox.critical(self, 'Error', f'Error during processing: {str(e)}')


class BareEarthReconstructor:
    def __init__(self, iface):
        self.iface = iface
        self.dlg = None
        self.action = None

    def initGui(self):
        self.action = QAction('Bare Earth Reconstructor', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Bare Earth Reconstructor', self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu('&Bare Earth Reconstructor', self.action)
            self.action = None

    def run(self):
        if not self.dlg:
            self.dlg = BareEarthReconstructorDialog()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow() 