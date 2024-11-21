# OS-specific installation instructions for yle-dl

## Debian and Ubuntu

```
sudo apt install pipx
pipx ensurepath
pipx install yle-dl
```

## Installing from source code on Debian 12 (Bookworm)/Ubuntu 20.04 and later

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt install git wget ffmpeg python3-pip python3-pytest
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
python3 -m venv venv
source venv/bin/activate
pip3 install .

# Note that you need to always activate the virtual environment before running yle-dl
source yle-dl/venv/bin/activate
```

## Gentoo

```
emerge -av yle-dl
```


## OpenSUSE Tumbleweed

```
# Install non-free codecs
sudo zypper addrepo -f http://packman.inode.at/suse/openSUSE_Tumbleweed/ packman
sudo zypper install --allow-vendor-change ffmpeg-4
sudo zypper dup --allow-vendor-change --from http://packman.inode.at/suse/openSUSE_Tumbleweed/

# Dependencies
sudo zypper install python3-pip python3-requests python3-lxml wget

# Install the yle-dl
pip3 install --user --upgrade yle-dl
```

Non-free codecs can be installed in a similar way on OpenSUSE Leap
15.2 except that there are no packages available for ffmpeg-4, only
for ffmpeg-3. Older ffmpeg means that subtitles will not be downloaded
correctly.


## Mac OS X

First, install [Homebrew](https://brew.sh/). Next, run the following
commands:

```
brew install python
brew install wget
brew install ffmpeg
brew install yle-dl
```


## Windows 10

### Python

Download the latest Python 3 release from
https://www.python.org/downloads/windows/ and install it in C:\somepath\Python.

Append the following paths to the PATH environment variable in Control
Panel > System and security > System > Advanced system settings >
Environment Variables...:
```
C:\somepath\Python\Python36
C:\somepath\Python\Python37
C:\somepath\Python\Python36\Scripts
C:\somepath\Python\Python37\Scripts
%USERPROFILE%\AppData\Roaming\Python\Python36\Scripts
%USERPROFILE%\AppData\Roaming\Python\Python37\Scripts
```

### ffmpeg

Download the binary from
https://ffmpeg.org/download.html#build-windows. Select the latest
release build (not a nightly git build), Windows 64-bit, Static.
Extract the zip in `C:\somepath\ffmpeg`.

Append `C:\somepath\ffmpeg\bin` to the PATH environment variable.

### wget

Download the latest wget.exe from https://eternallybored.org/misc/wget
and copy it to C:\somepath\wget.

Append `C:\somepath\wget` to the PATH environment variable.

### yle-dl

```
pip install --user --upgrade yle-dl
```

Usage:

```
yle-dl --vfat https://areena.yle.fi/...
```


## Android

Install [Termux](https://termux.com/).

Run on the Termux terminal:
```
pkg install python make clang libgmp wget ffmpeg libxml2 libxml2-utils libxslt
pip install lxml yle-dl
```
