prefix=/usr/local
BINDIR=$(DESTDIR)/$(prefix)/bin

all:

install:
	-mkdir -p $(BINDIR)
	cp yle-dl $(BINDIR)

uninstall:
	rm -f $(BINDIR)/yle-dl

# Uninstall librtmp and plugin installed by pre-2.0 versions
plugindir=$(prefix)/lib/librtmp/plugins
mandir=$(prefix)/man
libdir=$(prefix)/lib
PLUGINDIR=$(DESTDIR)$(plugindir)
MANDIR=$(DESTDIR)$(mandir)
LIBDIR=$(DESTDIR)$(libdir)
uninstall-old-rtmpdump:
	rm -f $(BINDIR)/rtmpdump
	rm -f $(PLUGINDIR)/yle.*
	rm -f $(LIBDIR)/librtmp.*
	rm -f $(LIBDIR)/pkgconfig/librtmp.pc
	rm -f $(MANDIR)/man1/rtmpdump.1
	rm -f $(MANDIR)/man3/librtmp.3
	rm -f $(MANDIR)/man8/rtmpgw.8
