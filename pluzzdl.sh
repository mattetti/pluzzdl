#!/bin/bash

MAIN="src/main.py"

if [ ! -z "`python --version 2>&1 | grep 'Python 2'`" ]
then
	python $MAIN $*
else
	if [ -x "/usr/bin/python2" ]
	then
		python2 $MAIN $*
	else
		if [ -x "/usr/bin/python2.7" ]
		then
			python2.7 $MAIN $*
		else
			if [ -x "/usr/bin/python2.6" ]
			then
				python2.6 $MAIN $*
			else
				echo "Erreur : impossible de trouver une version de Python 2"
			fi
		fi
	fi
fi
