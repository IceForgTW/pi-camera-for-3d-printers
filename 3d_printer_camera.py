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
    completed_timelapse_folder = '/completed_timelapses'
    threshold_percentage = float(0.965)
    timelapse_delay = 1  # delay in seconds
    begin_timelapse_delay = 420  # 5 minute delay to allow for heating and such
    camera = picamera.PiCamera()
    upload_skip = False

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
        logging.debug("First baseline check succeeded!")
        if compute_ssim(y, z) > settings.threshold_percentage:
            logging.debug("Second baseline check succeeded!")
            if compute_ssim(z, x) > settings.threshold_percentage:
                logging.info("Successfully created baseline!")
                settings.baseline_image = settings.stills_folder +\
                    baseline_images[0]
                return True
            else:
                logging.debug("Third baseline check failed!")
                return None
        else:
            logging.debug("Second baseline check failed!")
            return None
    else:
        logging.debug("First baseline check failed!")
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
        else:
            return False

    if(compute_ssim(settings.stills_folder + new_pic,
                    settings.stills_folder + old_pic) >
       settings.threshold_percentage):
        return True

    # if we get here, nothing has gotten past the threshold percentage.
    return False


def rename_timelapse(movie, folder_contents):
    '''Take the completed video and rename it based on whether or not there are
    others already in the folder we're looking at. Pass in a list of the names
    of items in the target folder for folder_contents.'''

    last_dot = movie.rfind(".")

    for ftu in xrange(99):
        before_last_dot = movie[:last_dot]
        after_last_dot = movie[last_dot:]

        if(before_last_dot + str(ftu) + after_last_dot not in
                folder_contents):
            new_movie_name = before_last_dot + str(ftu) +\
                after_last_dot

            # gotta rename it so now we can upload it or do whatever to it
            shutil.move(movie, new_movie_name)
            movie = new_movie_name
            return movie


def upload_movie(file_to_upload, settings=settings):

    if not settings.upload_skip:
        try:
            logging.info("Attempting to upload finished file via FTP!")

            session = ftplib.FTP(settings.ftp_host)
            session.login(settings.ftp_username, settings.ftp_password)

            # check to see if there's already a timelapse.avi there
            # if so, create a timelapse1.avi and so on and so forth
            session_contents = []
            session.retrlines("NLST", session_contents.append)
            if file_to_upload in session_contents:
                file_to_upload = rename_timelapse(file_to_upload,
                                                  session_contents)

            # file to send
            new_file = open(str(os.getcwd() + "/" + file_to_upload), 'rb')
            # send the file

            session.storbinary('STOR {}'.format(file_to_upload), new_file)
            new_file.close()  # close file and FTP
            session.quit()

            logging.info("Successfully uploaded finished timelapse!!!")
            os.remove(file_to_upload)

            return

        except Exception as e:
            log_error("Something has gone wrong with the FTP process!",
                      e)

    # we want this to run either if skip is set or the upload fails, so we put
    # it down here.

    logging.info("Moving timelapse to completed folder.")

    completed_files = []
    for (dirpath, dirnames, filenames) in os.walk(
            settings.completed_timelapse_folder):
        completed_files.extend(filenames)
        break
    if file_to_upload in completed_files:
        file_to_upload = rename_timelapse(file_to_upload, completed_files)

    shutil.move(file_to_upload,
                settings.completed_timelapse_folder + file_to_upload)


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


# **************************************************
# Program Logic
# **************************************************

def set_up(settings=settings):
    '''for items that only need to get run once'''

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
            logging.debug("Loaded setting for FTP came up empty. Setting to "
                          "None!")
            logging.info("Settings for FTP are not set. Skipping FTP upload.")
            settings.upload_skip = True

    settings.stills_folder = config.get('Info', 'stills_folder_location')

    if not (settings.stills_folder.endswith("/") or
            settings.stills_folder.endswith("\\")):
        # /folder becomes /folder/
        settings.stills_folder = settings.stills_folder + "/"

    if not (settings.stills_folder.startswith("/") or
            settings.stills_folder.startswith("\\")):
        settings.stills_folder = "/" + settings.stills_folder

    settings.stills_folder = os.getcwd() + settings.stills_folder
    settings.completed_timelapse_folder = os.getcwd() +\
        settings.completed_timelapse_folder


def main(settings=settings):

    # this is for resetting the values after the program has started
    # started another timelapse
    settings.currently_recording = False
    settings.picture_count = 0
    beginning_recording_check = [True for _ in range(6)]
    picture_list_check = []
    settings.pic_name = "pic00000.jpg"

    if not os.path.exists(settings.stills_folder):
        logging.debug(
            "Stills folder {} doesn't exist! Creating!".format(
                settings.stills_folder
            )
        )
        os.mkdir(settings.stills_folder)

    if not os.path.exists(settings.completed_timelapse_folder):
        logging.debug("Completed timelapse folder does not exist. Creating!")
        os.mkdir(settings.completed_timelapse_folder)

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

                beginning_recording_check.append(
                    threshold_check(settings.pic_name))
                beginning_recording_check.pop(0)
                logging.debug("beginning_recording_check = {}".format(
                    beginning_recording_check))

                if True not in beginning_recording_check:
                    settings.currently_recording = True
                    settings.recording_start_time = int(time.time())

                    if settings.picture_count - 7 < 0:
                        settings.recording_start_picture_count = 0
                    else:
                        settings.recording_start_picture_count = \
                            settings.picture_count - 7

                oldest_pic = (settings.stills_folder + "pic{}.jpg".
                              format(str(settings.picture_count - 10).
                                     zfill(5)))
                logging.debug("Oldest pic: {}".format(oldest_pic))

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

                    picture_list_check.append(
                            threshold_check(settings.pic_name,
                                            pic_minus_seven))

                    if len(picture_list_check) > 10:
                        # remove the first item in the list. That way the list
                        # constantly cycles through results.
                        picture_list_check.pop(0)
                        logging.debug(picture_list_check)
                        if False not in picture_list_check:
                            logging.debug("picture_list_check returned all "
                                          "True. Starting movie creation.")

                            settings.currently_recording = False
                            create_movie()
                            upload_movie('timelapse.avi')
                            # we made it this far, so restart the whole
                            # process!
                            shutil.rmtree(settings.stills_folder)
                            break
                    else:
                        logging.debug("picture_list_check is not long enough"
                                      " to begin checking.")

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
    set_up()
    while True:
        main()
