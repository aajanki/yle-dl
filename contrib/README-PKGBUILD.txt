PKGBUILD is a package builder script for Arch Linux.

Installation

Go to folder where "PKGBUILD" -file is located.

Type command:	(with sudo: sudo makepkg -c --asroot)
	makepkg -c

It makes now new *.tar.xz -file.


Type command:			(new *.tar.xz -file)
	pacman -U '/yle-dl-arch/yle-dl-2.1.0_9-x86_64.pkg.tar.xz'


Normal version was broken because python command;
Source: https://wiki.archlinux.org/index.php/python

And this checks that you have right depencies.


Uninstalling:
rm -f '/usr/local/bin/yle-dl' 



Notes:
UPDATE - No need anymore Branch's commit id mess. :) 
PKGBUILD "_commit" needs to be updated when Branch's commit id 
updates to different. ()
