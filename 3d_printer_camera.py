#!/usr/local/bin/python
# -*- coding: utf-8 -*-

'''
*********************************************
 File Name: 3d_printer_camera.py
 Python Version: 2.7.11
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

import ftplib
import logging
import os
import shutil
import subprocess
import sys
import time

from time import sleep
from ssim import compute_ssim

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

global settings


class settings:
    stills_folder = 'stills'
    threshold_percentage = float(0.968)
    timelapse_delay = 1  # delay in seconds
    begin_timelapse_delay = 420  # 5 minute delay to allow for heating and such
    camera = picamera.PiCamera()

    # ignore the ones below; they get changed in runtime

    baseline_picture = None
    currently_recording = False
    picture_count = 0
    recording_start_picture_count = 0
    pic_name = ""
    ftp_host = ""
    ftp_username = ""
    ftp_password = ""


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
    logging.basicConfig(level=logging.DEBUG,
                        datefmt='%m/%d/%Y %I:%M:%S %p',
                        filename='3d_printer_camera.log')
    console = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] - [%(levelname)s] - '
                                  '%(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)


def log_error(message, e):
    '''Sends the error and all of its details to logging.error with the custom
    message passed to the function.'''
    logging.error("{}\n\n{}: {}".format(message, type(e).__name__, ', '.join(
                                         map(str, e.args))))


def capture_baseline(settings=settings):
    '''Used to create the first image, the one that determines when to begin
    actually creating the timelapse.'''

    baseline_images = ['baseline1.jpg', 'baseline2.jpg', 'baseline3.jpg']
    # we set this here so we can remove the baseline on keyboard interrupt
    # in main()
    settings.baseline_images = baseline_images

    for picture in baseline_images:
        sleep(1)
        logging.debug("Capturing baseline image {}".format(picture))
        take_picture(picture)

    x = settings.stills_folder + baseline_images[0]
    y = settings.stills_folder + baseline_images[1]
    z = settings.stills_folder + baseline_images[2]

    if(compute_ssim(x, y) > settings.threshold_percentage):
        if compute_ssim(y, z) > settings.threshold_percentage:
            if compute_ssim(z, x) > settings.threshold_percentage:
                logging.info("Successfully created baseline!")
                settings.baseline_image = settings.stills_folder +\
                    baseline_images[0]
                return True
            else:
                return None
        else:
            return None
    else:
        return None


def take_picture(picname, camera=settings.camera):
    camera.capture(settings.stills_folder + picname)


def threshold_check(new_pic, old_pic=None, settings=settings):
    if old_pic:
        logging.debug("Checking threshold of {} vs {}".format(
                      new_pic, old_pic))
    else:
        logging.debug("Checking threshold of {}".format(new_pic))

    if old_pic is None:
        old_pic = settings.baseline_image
        if(compute_ssim(settings.stills_folder + new_pic,
                        old_pic) > settings.threshold_percentage):
            return True

    if(compute_ssim(settings.stills_folder + new_pic,
                    settings.stills_folder + old_pic) >
       settings.threshold_percentage):
        return True

    # if we get here, nothing has gotten past the threshold percentage.
    return False


def upload_movie(file_to_upload, settings=settings):

    if file_to_upload is None:
        logging.error("Upload movie has received a None object! "
                      "Skipping upload!")
    return

    if settings.ftp_host is None:
        logging.error("No FTP host has been set! Skipping upload!")
        return

    if settings.ftp_username is None:
        logging.error("No username has been given for FTP uploading!"
                      " Skipping upload!")
        return

    if settings.ftp_username is None:
        logging.error("No password has been set for FTP uploading!"
                      " Skipping upload!")
        return

    try:
        logging.info("Attempting to upload finished file via FTP!")

        session = ftplib.FTP(settings.ftp_host)
        session.login(settings.ftp_username, settings.ftp_password)

        # check to see if there's already a timelapse.avi there
        # if so, create a timelapse1.avi and so on and so forth
        session_contents = []
        session.retrlines("NLST", session_contents.append)
        if file_to_upload in session_contents:
            last_dot = file_to_upload.rfind(".")
            for ftu in xrange(99):
                before_last_dot = file_to_upload[:last_dot]
                after_last_dot = file_to_upload[last_dot:]

                if(before_last_dot + str(ftu) + after_last_dot not in
                        session_contents):
                    new_file_to_upload = before_last_dot + str(ftu) +\
                        after_last_dot

                    # gotta rename it so now we can upload it
                    shutil.move(file_to_upload, new_file_to_upload)
                    file_to_upload = new_file_to_upload
                    break

        # file to send
        new_file = open(str(os.getcwd() + "/" + file_to_upload), 'rb')
        # send the file

        session.storbinary('STOR {}'.format(file_to_upload), new_file)
        new_file.close()  # close file and FTP
        session.quit()

        logging.info("Successfully uploaded finished timelapse!!!")
        os.remove(file_to_upload)

    except Exception as e:
        log_error("Something has gone wrong with the FTP process!",
                  e)


def create_movie():
    logging.info("Creating timelapse; here we go!")
    try:
        print(settings.recording_start_picture_count)

        process_call = 'gst-launch-1.0 multifilesrc location=stills/pic%05d.'\
                       'jpg start-index={} caps="image/jpeg,framerate=24/1" '\
                       '! jpegdec ! omxh264enc ! avimux ! filesink location='\
                       'timelapse.avi'.format(int(settings.
                            recording_start_picture_count+1))
        # we define the call above in order to get around a limitation of
        # subprocess Popen which requires the command to be completely typed
        # as if you were putting it into the console.
        subprocess.call(process_call, shell=True)
        subprocess.call('sync', shell=True)
    except Exception as e:
        log_error("Something went wrong during the creation of the timelapse."
                  "Error log here:", e)
        return

    upload_movie('timelapse.avi')


# **************************************************
# Program Logic
# **************************************************


def main(settings=settings):

    # this is for resetting the values after the program has started
    # started another timelapse
    settings.currently_recording = False
    settings.picture_count = 0
    picture_list_check = []
    final_list_check = [False for _ in range(15)]

    logging.info("Starting program!")

    config = configparser.ConfigParser(allow_no_value=True)

    if os.path.isfile("./config.ini"):
        config.read('config.ini')
    else:
        generate_config()

    logging.debug("Loading in config file...")
    settings.ftp_host = config.get('Info', 'ftp_host')
    settings.ftp_username = config.get('Info', 'ftp_username')
    settings.ftp_password = config.get('Info', 'ftp_password')

    loaded_settings = [settings.ftp_host, settings.ftp_username,
                       settings.ftp_password]

    for setting in loaded_settings:
        if setting == "":
            setting = None
            logging.debug("Loaded setting {} came up empty. Setting to "
                          "None!".format(setting.__name__))

    settings.stills_folder = config.get('Info', 'stills_folder_location')

    if(settings.stills_folder[-1:] != "/" or
            settings.stills_folder[-1:] != "\\"):
        # /folder becomes /folder/
        settings.stills_folder = settings.stills_folder + "/"

    if(settings.stills_folder[:1] != "/" or
            settings.stills_folder[:1] != "\\"):
        settings.stills_folder = "/" + settings.stills_folder

    settings.stills_folder = os.getcwd() + settings.stills_folder

    settings.pic_name = "pic00000.jpg"

    if not os.path.exists(settings.stills_folder):
        logging.debug(
            "Stills folder {} doesn't exist! Creating!".format(
                settings.stills_folder
            )
        )
        os.mkdir(settings.stills_folder)

    # Here we get our first image; we assume at this point that the camera is
    # oriented where it needs to go and that everything is prepared for the
    # upcoming print.
    while True:
        settings.baseline_size = capture_baseline()
        if settings.baseline_size is not None:
            break
    # now that we have our baseline size, we can start doing timelapse images
    # and keeping track of what we have.

    try:

        while True:
            sleep(settings.timelapse_delay)

            settings.picture_count += 1
            settings.pic_name = "pic{}.jpg".format(str(settings.
                                                   picture_count).zfill(5))
            take_picture(settings.pic_name)

            if not settings.currently_recording:

                if not threshold_check(settings.pic_name):
                    settings.currently_recording = True
                    settings.recording_start_time = int(time.time())

                if settings.picture_count - 5 < 0:
                    settings.recording_start_picture_count = 0
                else:
                    settings.recording_start_picture_count = \
                        settings.picture_count - 5

                    oldest_pic = (settings.stills_folder + "pic{}.jpg".
                                  format(str(settings.picture_count - 5).
                                         zfill(5)))

                    if os.path.exists(oldest_pic):
                        os.remove(oldest_pic)

            else:
                if int(time.time()) < (settings.recording_start_time +
                                       settings.begin_timelapse_delay):
                    logging.debug("Recording time has been triggered. {}"
                                  " seconds left before beginning "
                                  "threshold checks again.".format(
                                    abs((settings.begin_timelapse_delay +
                                         settings.recording_start_time) -
                                        int(time.time()))))
                    # we ignore basically everything for the beginning delay
                    # and assume that everything that happens is part of the
                    # video
                else:
                    pic_minus_seven = "pic{}.jpg".format(str(
                                        settings.picture_count - 7).zfill(5))
                    final_picture_list = ["pic{}.jpg".
                                          format(str(settings.picture_count-1).
                                                 zfill(5)),
                                          "pic{}.jpg".
                                          format(str(settings.picture_count-2).
                                                 zfill(5)),
                                          "pic{}.jpg".
                                          format(str(settings.picture_count-3).
                                                 zfill(5)),
                                          "pic{}.jpg".
                                          format(str(settings.picture_count-4).
                                                 zfill(5)),
                                          "pic{}.jpg".
                                          format(str(settings.picture_count-5).
                                                 zfill(5))
                                          ]

                    picture_list_check.append(
                            threshold_check(settings.pic_name,
                                            pic_minus_seven))

                    if len(picture_list_check > 15):
                        # remove the first item in the list. That way the list
                        # constantly cycles through results.
                        picture_list_check.pop(0)
                        logging.debug(picture_list_check)
                        if False not in picture_list_check:
                            logging.debug("picture_list_check returned all "
                                          "True. Starting final check.")
                            for older_pic in final_picture_list:
                                final_list_check.append(
                                    threshold_check(settings.pic_name,
                                                    older_pic))
                            logging.debug("Final picture list: {}".format(
                                final_picture_list))
                            if False not in final_list_check:
                                settings.currently_recording = False
                                create_movie()
                                # we made it this far, so restart the whole
                                # process!
                                shutil.rmtree(settings.stills_folder)
                                break

    except KeyboardInterrupt:
        # we don't need the baseline images anymore
        for picture in settings.baseline_images:
            os.remove(settings.stills_folder + picture)
        logging.error("Keyboard interrupt has been triggered. "
                      "Stopping program.")
        sys.exit(1)

if __name__ == '__main__':

    start_logging()
    settings = settings()
    while True:
        main()
