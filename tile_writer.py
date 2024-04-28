# tile_writer.py
# Version 0.2.2 2018-11-09
# Copyright 2018 Alexander Hajnal All rights reserved

# This software is released under the terms of the Version 3 of the GNU Affero
# General Public License.  See the LICENSE file for details

# Generates slippy map tiles from within QGIS

# See the readme.txt file for usage instructions

# Email:   SLIPPYsoftware@alephnull.net
#          (remove the type of map to get the real address)
# Website: http://alephnull.net/software/gis/tile_writer.shtml
# Github:  https://github.com/Alex-Kent/tile_writer

# ==============================================================================

# Start user-editable settings

# Minimum zoom level
start_z = 10

# Maximum zoom level
end_z = 15

# How many map tiles to place in each regional tile
# (the actual number of map tiles per regional tile is step * step)
# Higher number speed up rendering (assuming enough RAM is available).
# Lower numbers decrease memory usage but increase rendering time.
step = 16

# Number of extra map tiles to render along each edge of a regional tile
# By rendering extra, unused border tiles we can avoid shifting labels,
# truncated images, and line-drawing inconsistancies at tile boundaries.
# If this value is set to 0 you will encounter rendering issues at tile
# boundaries.
border = 2

# Directory to write the regional images and level subdirectories to
output_path = '.'

# Path of shapefile defining the area of interest
# The extent of the shapefile is used to limit rendering to a particular area.
# Note that no clipping is done so at lower zoom levels tiles from outside the
# area of interest will be generated.
area_of_interest = 'border.shp'

# Filename convention to follow
#tile_format = 'google'
tile_format = 'tms'

# End user-editable settings

# ==============================================================================

from PyQt5.QtCore import *
from PyQt5.QtGui import *

from qgis.core import *
import qgis.utils
from qgis.utils import iface
from qgis.gui import *

import sys
import os
import os.path
import shutil
import math

from globalmercator import GlobalMercator

def delay(millisecondsToWait):
    dieTime = QTime().currentTime().addMSecs(millisecondsToWait)
    while QTime.currentTime() < dieTime:
        QCoreApplication.processEvents(QEventLoop().AllEvents, 100)

borderLayer = QgsVectorLayer(area_of_interest, 'border', 'ogr')
borderRect = borderLayer.extent()
borderCRS = borderLayer.crs()

mapRect = QgsCoordinateTransform(borderCRS, QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance()).transform(borderRect) # WGS84

xStart = mapRect.xMinimum()
xEnd = mapRect.xMaximum()

yStart = mapRect.yMinimum()
yEnd = mapRect.yMaximum()

width = mapRect.width()
height = mapRect.height()

print(f"xStart: {xStart}")
print(f"xEnd:   {xEnd}")
print()
print(f"yStart: {yStart}")
print(f"yEnd:   {yEnd}")
print()
print(f"width:  {width}")
print(f"height: {height}")

print()

for z in range(start_z, end_z + 1, 1):
    print()
    print(f"zoom:{z}  step:{step}  border_size:{border}")

    gm = GlobalMercator()

    lon = xStart
    lat = yStart
    mx_min, my_min = gm.LatLonToMeters(lat, lon)
    tx_min, ty_min = gm.MetersToTile(mx_min, my_min, z)
    print(f"Min: {tx_min}, {ty_min} @ {z}")

    lon = xEnd
    lat = yEnd
    mx_max, my_max = gm.LatLonToMeters(lat, lon)
    tx_max, ty_max = gm.MetersToTile(mx_max, my_max, z)
    print(f"Max: {tx_max}, {ty_max} @ {z}")

    dirPath = f"{output_path}/{z}"
    QDir().mkpath(dirPath)

    width = 256 * (step + border + border)
    height = 256 * (step + border + border)

    print()
    print("While generating the regional tiles, QGIS may appear to have locked up.")
    print("This is not the case.  Please be patient.")
    print()

    tx = tx_max - tx_min + 1
    ty = ty_max - ty_min + 1
    rtx = math.ceil(tx / step)
    rty = math.ceil(ty / step)
    print(f"Generating regional tiles... ({tx} x {ty} tiles -> {rtx} x {rty} regional tiles)")

    total_regional_tiles = 0
    for x in range(tx_min, tx_max + 1, step):
        for y in range(ty_min, ty_max + 1, step):
            total_regional_tiles += 1
            imagePath = f"{output_path}/{z}_{x}_{y}_s{step}_b{border}.png"
            lat_min, lon_min, ignore, ignore = gm.TileLatLonBounds(x - border, y - border, z)
            ignore, ignore, lat_max, lon_max = gm.TileLatLonBounds(x + step + border - 1, y + step + border - 1, z)
            lat_min, lon_min = gm.LatLonToMeters(lat_min, lon_min)
            lat_max, lon_max = gm.LatLonToMeters(lat_max, lon_max)
            if os.path.isfile(imagePath):
                # Regional tile exists, so skip it
                print("o", end="", flush=True)
            else:
                image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)

                settings = QgsMapSettings()
                settings.setOutputDpi(95.0)
                settings.setOutputImageFormat(QImage.Format_ARGB32_Premultiplied)
                settings.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
                settings.setOutputSize(QSize(width, height))
                settings.setLayers(QgsProject.instance().layerTreeRoot().checkedLayers())
                settings.setFlag(QgsMapSettings.DrawLabeling, True)
                settings.setBackgroundColor(QColor(127, 127, 127, 0))

                tileRect = QgsRectangle(lat_min, lon_min, lat_max, lon_max)
                settings.setExtent(tileRect)

                job = QgsMapRendererSequentialJob(settings)
                job.start()
                job.waitForFinished()
                delay(10)
                image = job.renderedImage()
                image.save(imagePath, "PNG")
                print("*", end="", flush=True)
        print()

    print()

    print("Splitting regional tiles into TMS tiles...")
    h = 256 * (border + border + step)
    current_regional_tile = 1
    for x in range(tx_min, tx_max + 1, step):
        for y in range(ty_min, ty_max + 1, step):
            srcPath = f"{output_path}/{z}_{x}_{y}_s{step}_b{border}.png"
            if os.path.isfile(srcPath):
                print()
                print(f"Processing regional tile {current_regional_tile} of {total_regional_tiles}: {srcPath}")
                current_regional_tile += 1
                srcImage = QImage()
                srcImage.load(srcPath)
                px = 256 * border
                for tile_x in range(x, x + step, 1):
                    iDirPath = f"{output_path}/{z}/{tile_x}"
                    QDir().mkpath(iDirPath)
                    py = 256 * (border + 1)
                    for tile_y in range(y, y + step, 1):
                        if tile_format == 'tms':
                            tile_y_tms = (1 << z) - tile_y - 1
                            dstPath = f"{output_path}/{z}/{tile_x}/{tile_y_tms}.png"
                        else:
                            dstPath = f"{output_path}/{z}/{tile_x}/{tile_y}.png"
                        if os.path.isfile(dstPath):
                            # Tile exists, so skip it
                            print("o", end="", flush=True)
                        else:
                            dstImage = srcImage.copy(px, h - py, 256, 256)
                            dstImage.save(dstPath, "PNG")
                            print("*", end="", flush=True)
                        py += 256
                    print()
                    px += 256

print()
print("All done!")


# Warranty
# ------------------------------------------------------------------------------
# I make no warranty or representation, either express or implied, with respect
# the behavior of this script, its quality, performance, accuracy, merchantability,
# or fitness for a particular purpose. This script is provided 'as is', and
# you, by making use thereof, are assuming the entire risk.  That said,
# I hope you this script useful.  Have fun!
