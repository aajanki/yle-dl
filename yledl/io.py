# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import os
import os.path
import sys
from pkg_resources import resource_filename


def which(program):
    """Search for program on $PATH and return the full path if found."""
    # Adapted from http://stackoverflow.com/questions/377017
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def find_rtmpdump(rtmpdump_arg):
    binary = rtmpdump_arg

    if not binary:
        if sys.platform == 'win32':
            binary = which('rtmpdump.exe')
        else:
            binary = which('rtmpdump')
    if not binary:
        binary = 'rtmpdump'

    return binary


def convert_hds_argument(arg):
    if arg:
        return arg.split(' ')
    else:
        return ['php', resource_filename(__name__, 'AdobeHDS.php')]


def convert_download_limits(arg):
    return arg or DownloadLimits()


def ffmpeg_default(arg):
    return arg or 'ffmpeg'


def ffprobe_default(arg):
    return arg or 'ffprobe'


def wget_default(arg):
    return arg or 'wget'


@attr.s
class DownloadLimits(object):
    duration = attr.ib(default=None)
    ratelimit = attr.ib(default=None)


@attr.s
class IOContext(object):
    outputfilename = attr.ib(default=None)
    destdir = attr.ib(default=None)
    resume = attr.ib(default=False)
    download_limits = attr.ib(default=None, converter=convert_download_limits)
    excludechars = attr.ib(default='*/|')
    proxy = attr.ib(default=None)
    rtmpdump_binary = attr.ib(default=None, converter=find_rtmpdump)
    hds_binary = attr.ib(default=None, converter=convert_hds_argument)
    ffmpeg_binary = attr.ib(default='ffmpeg', converter=ffmpeg_default)
    ffprobe_binary = attr.ib(default='ffprobe', converter=ffprobe_default)
    wget_binary = attr.ib(default='wget', converter=wget_default)
