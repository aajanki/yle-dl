prefix=/usr/local

BINDIR=$(DESTDIR)/$(prefix)/bin
plugindir=$(prefix)/lib/librtmp/plugins
PLUGINDIR=$(DESTDIR)$(plugindir)
INCLUDEDIR=$(prefix)/include

SYS=posix

SOX_posix=so
SOX_darwin=dylib
SOX_mingw=so	# useless
SOX=$(SOX_$(SYS))
SO_posix=so.0
SO_darwin=0.so
SO_mingw=dll
SO_EXT=$(SO_$(SYS))

SO_LDFLAGS_posix=-shared -Wl,-soname,$@
SO_LDFLAGS_darwin=-dynamiclib -twolevel_namespace -undefined dynamic_lookup \
	-fno-common -headerpad_max_install_names -install_name $(plugindir)/$@
SO_LDFLAGS_mingw=-shared -Wl,--out-implib,$@.a
SO_LDFLAGS=$(SO_LDFLAGS_$(SYS))

INSTALL_IMPLIB_posix=
INSTALL_IMPLIB_darwin=
INSTALL_IMPLIB_mingw=cp yle.dll $(PLUGINDIR)
INSTALL_IMPLIB=$(INSTALL_IMPLIB_$(SYS))

OPT=-O2
CFLAGS=-Wall -fPIC -I$(INCLUDEDIR) $(OPT)
LDFLAGS=-L../rtmpdump/librtmp -lrtmp

all: yle.$(SO_EXT)

yle.o: yle.c yle.h Makefile
	$(CC) $(CFLAGS) -c -o $@ $<

yle.$(SO_EXT): yle.o
	$(CC) $(SO_LDFLAGS) -o $@ $^ $(LDFLAGS)

install:
	mkdir -p $(PLUGINDIR)
	cp yle.$(SO_EXT) $(PLUGINDIR)
	cd $(PLUGINDIR); ln -sf yle.$(SO_EXT) yle.$(SOX)
	$(INSTALL_IMPLIB)

clean:
	rm -f *.o *.$(SOX) *.$(SO_EXT)
