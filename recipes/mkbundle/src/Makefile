SOURCES= \
	mkbundle.cs \
	reflect/*.cs \
	reflect/Emit/*.cs \
	reflect/Metadata/*.cs \
	reflect/Reader/*.cs \
	reflect/Writer/*.cs \
	reflect/Impl/*.cs

all:
	mcs -out:mkbundle.exe -target:exe -r:System.Security -resource:template.c -resource:template_main.c ${SOURCES}

