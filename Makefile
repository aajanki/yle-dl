prefix=/usr/local
BINDIR=$(DESTDIR)/$(prefix)/bin


all:
	@cd rtmpdump; $(MAKE)
	@cd plugin; $(MAKE) INCLUDEDIR=../rtmpdump

install:
	-mkdir -p $(BINDIR)
	cp yle-dl $(BINDIR)
	@cd rtmpdump; $(MAKE) install
	@cd plugin; $(MAKE) install

clean:
	@cd rtmpdump; $(MAKE) clean
	@cd plugin; $(MAKE) clean
