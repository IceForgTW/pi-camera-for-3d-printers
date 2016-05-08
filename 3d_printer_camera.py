#!/usr/local/bin/python
# -*- coding: utf-8 -*-

'''
*********************************************
 File Name: 3d_printer_camera.py
 Author: Joe Kaufeld
 Email: joe.kaufeld@gmail.com
 Purpose:
   Runs a constant camera stream to attempt to auto-detect 3D prints,
   photograph them, and use the photographs to create a timelapse of the final
   build.
 Notes:
   This program was written for Wil Marquez of the Design Bank in
   Indianapolis, Indiana, USA. It is with his permission that this code is up
   and available. If you'd like more information about the Design Bank and
   their work with fostering creativity in inner city youth, feel free to
   contact him here: design@wpurpose.com
*********************************************
'''

from __future__ import division
from __future__ import print_function

import logging
import os
import sys

from time import sleep

if sys.version_info.major < 3:
    import ConfigParser as configparser
else:
    import configparser

try:
    import picamera
except ImportError:
    print("This is a camera application, and you're missing the library!"
          "\nPlease run sudo apt-get install python-picamera and run this "
          "application again!")
    sys.exit(1)


class settings:
    stills_folder = '.\stills'
    threshold_percentage = float(0.96)
    timelapse_delay = 10  # delay in seconds
    ftp_host = '127.0.0.1'
    ftp_username = 'test_user'
    ftp_password = 'asdf1234'

    # ignore the ones below; they get changed in runtime

    baseline_size = 0
    currently_recording = False
    picture_count = 0
    pic_name = ""


def generate_config(exit=True):

    config = configparser.ConfigParser(allow_no_value=True)
    config.read('config.ini')

    config.add_section('Info')
    config.set('Info', '; The below information is used for uploading '
               'completed videos to an ftp server.')
    config.set('Info', 'ftp_host', settings.ftp_host)
    config.set('Info', 'ftp_username', settings.ftp_username)
    config.set('Info', 'ftp_password', settings.ftp_password)
    config.set('Info', 'stills_folder_location', settings.stills_folder)

    with open('config.ini', 'w') as f:
        config.write(f)

    config_nonexist_error = 'Configuration not found, a default config.ini '\
                            'was created.\n'\
                            'You must edit it before using this script.\n\n'\
                            'Application exiting.'

    if exit:
        print(config_nonexist_error)
        sys.exit()


def start_logging():
    logging.basicConfig(level=logging.INFO,
                        datefmt='%m/%d/%Y %I:%M:%S %p',
                        filename='3d_printer_camera.log')
    console = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] - [%(levelname)s] - '
                                  '%(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)


def average(numbers):
    # you'd think there would be an actual python builtin for 'average'. What
    # the hell, guys?
    if len(numbers) > 0:
        return float(sum(numbers))/len(numbers)
    else:
        return None


def get_image_size(image):
    logging.debug("Getting image size of image {}".format(image))
    return os.path.getsize(settings.stills_folder + '\\' + image)


def capture_baseline(camera):
    baseline_images = ['baseline1.jpg', 'baseline2.jpg', 'baseline3.jpg']
    settings.baseline_sizes_temp = []

    for picture in baseline_images:
        logging.debug("Capturing baseline image {}".format(picture))
        take_picture(picture)

        new_image_size = get_image_size(picture)

        logging.debug("{} size for baseline average: {}".format(
            picture, new_image_size))

        settings.baseline_sizes_temp.append(new_image_size)

    settings.baseline_size = average(settings.baseline_sizes_temp)
    logging.info("Baseline image size: {}".format(settings.baseline_size))

    # we don't need the baseline images anymore now that we have the
    # information that we need
    for picture in baseline_images:
        os.remove(settings.stills_folder + "\\" + picture)


def take_picture(camera, picname):
    camera.capture(settings.stills_folder + '\\' + picname)
    pass


def threshold_check(new_pic):
    logging.debug("Checking threshold of {}".format(new_pic))
    # we create an otherwise unnecessary variable here in order to avoid
    # making 4 os calls every threshold check
    new_pic_size = get_image_size(new_pic)

    t_variance = (new_pic_size -
                  (new_pic_size *
                   settings.threshold_percentage))

    if (settings.baseline_size < (new_pic_size + t_variance) or
            settings.baseline_size > (new_pic_size - t_variance)):
        logging.debug("New pic {} has size {}, currently outside of threshold"
                      " {}. Starting recording!".format(new_pic,
                                                        new_pic_size,
                                                        settings.baseline_size
                                                        ))
        return True
    else:
        logging.debug("New pic {} has size {}, inside the threshold for "
                      "change. Continuing as before!".format(new_pic,
                                                             new_pic_size))
        return False


# **************************************************
# Program Logic
# **************************************************


def main():

    config = configparser.ConfigParser(allow_no_value=True)

    if os.path.isfile("./config.ini"):
        config.read('config.ini')
    else:
        generate_config()

    # read configuration file
    settings.ftp_host = config.get('Info', 'ftp_host')
    settings.ftp_username = config.get('Info', 'ftp_username')
    settings.ftp_password = config.get('Info', 'ftp_password')
    settings.stills_folder = config.get('Info', 'stills_folder_location')

    camera = picamera.PiCamera()
    settings.pic_name = "pic{}.jpg".format(settings.picture_count)
    if not os.path.exists(settings.stills_folder):
        logging.debug(
            "Stills folder {} doesn't exist! Creating!".format(
                settings.stills_folder
            )
        )
        os.mkdirs(settings.stills_folder)

    # The actual detection logic is aiming for something super-ridiculous-
    # simple. When the program first starts, we take three "starter" images in
    # rapid succession. These are our baseline images, and from there the file
    # size is checked on all of them and then averaged. That's our baseline
    # image. For each image that's taken after that, the filesize is checked
    # against our baseline. If it's outside our threshold, we can reasonably
    # assume that the contents of the image have changed enough that we should
    # start paying attention to the images.
    #
    # Sure, we could really get into it with histograms or root-mean-square
    # differences, but this is designed to run on a Raspberry Pi, and probably
    # an old one at that. There's really no need for all that overhead, so here
    # we go!

    settings.baseline_size = capture_baseline(camera)

    # now that we have our baseline size, we can start doing timelapse images
    # and keeping track of what we have.

    while True:
        sleep(settings.timelapse_delay)

        settings.picture_count += 1
        take_picture(camera, settings.pic_name)

        if threshold_check(settings.pic_name):
            settings.currently_recording = True

        if not settings.currently_recording:

            oldest_pic = (settings.stills_folder + "\\" + "pic{}.jpg".
                          format(settings.picture_count - 5))
            if os.path.exists(oldest_pic):
                os.remove(oldest_pic)

        '''
        WHAT COMES NEXT?!?!?!?!
        '''

if __name__ == '__main__':

    start_logging()
    settings = settings()
    main()