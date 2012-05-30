prefix=/usr/local
SYS=posix

FINALDIR=$(DESTDIR)/$(prefix)
BINDIR=$(DESTDIR)/$(prefix)/bin

all:
	@cd rtmpdump; $(MAKE)
	@cd plugin; $(MAKE) INCLUDEDIR=../rtmpdump

install:
	-mkdir -p $(BINDIR)
	cp yle-dl $(BINDIR)
	@cd rtmpdump; $(MAKE) install
	@cd plugin; $(MAKE) install

ifeq ($(SYS),posix)
	@if [ $(FINALDIR) = "/usr/" -o $(FINALDIR) = "//usr" -o $(FINALDIR) = "/usr/local" -o $(FINALDIR) = "//usr/local" ]; then \
		/sbin/ldconfig; \
	fi
endif

clean:
	@cd rtmpdump; $(MAKE) clean
	@cd plugin; $(MAKE) clean
