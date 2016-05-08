# pi-camera-for-3d-printers

# important
Important note: I don't actually have the camera module with me, so most of this code is completely untested. I'll update this readme when I'm 100% sure that all this works!

# about
This program is designed to be started on system boot. How it works:

* When the program starts, it takes 3 pictures in rapid succession to establish a baseline.
* After it has an idea of what the current scene is, it continues taking pictures on the delay (default: 10 seconds)
* If enough changes between pictures, the program assumes that you've started a 3D print on the printer, at which point it begins saving the images.
* When enough of the pictures reach a similar threshold, it assumes the print has finished and will call ffmpeg to create a video of the stored images.
* On finishing the video, it will attempt to upload the file to an ftp service of your choice.
