all:
	@echo "MAKEFLAGS=[$(MAKEFLAGS)] first=[$(firstword -$(MAKEFLAGS))] i=[$(findstring i,$(firstword -$(MAKEFLAGS)))] s=[$(findstring s,$(firstword -$(MAKEFLAGS)))]"
