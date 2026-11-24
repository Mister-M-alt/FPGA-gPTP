FOO ?= base
run: export CCACHE_BASEDIR ?= /some/where
run:: first
	@echo "rule1 CCACHE_BASEDIR=[$$CCACHE_BASEDIR]"
run:: second
	@echo "rule2 CCACHE_BASEDIR=[$$CCACHE_BASEDIR]"
first second:
	@echo "$@ CCACHE_BASEDIR=[$$CCACHE_BASEDIR]"
