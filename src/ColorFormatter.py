#!/usr/bin/env python2
# -*- coding:Utf-8 -*-

# Adapted from :
#    Brandon Thomson
#    http://stackoverflow.com/questions/384076/how-can-i-make-the-python-logging-output-to-be-colored

import logging

class ColorFormatter( logging.Formatter ):

	FORMAT = ( "[%(levelname)-19s]  " "$BOLD%(filename)-20s$RESET" "%(message)s" )
	# FORMAT    = ( "[%(levelname)-18s]  " "($BOLD%(filename)s$RESET:%(lineno)d)  " "%(message)s"  )

	BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range( 8 )

	RESET_SEQ = "\033[0m"
	COLOR_SEQ = "\033[1;%dm"
	BOLD_SEQ = "\033[1m"

	COLORS = {
				'WARNING'  : YELLOW,
				'INFO'     : GREEN,
				'DEBUG'    : WHITE,
				'CRITICAL' : RED,
				'ERROR'    : RED
			 }

	def __init__( self, use_color ):
		self.use_color = use_color
		msg = self.formatter_msg( self.FORMAT )
		logging.Formatter.__init__( self, msg )

	def formatter_msg( self, msg ):
		if( self.use_color ):
			msg = msg.replace( "$RESET", self.RESET_SEQ ).replace( "$BOLD", self.BOLD_SEQ )
		else:
			msg = msg.replace( "$RESET", "" ).replace( "$BOLD", "" )
		return msg

	def format( self, record ):
		levelname = record.levelname
		if( self.use_color and levelname in self.COLORS ):
			fore_color = 30 + self.COLORS[ levelname ]
			levelname_color = self.COLOR_SEQ % fore_color + levelname + self.RESET_SEQ
			record.levelname = levelname_color
		return logging.Formatter.format( self, record )
