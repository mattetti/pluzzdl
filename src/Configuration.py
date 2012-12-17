#!/usr/bin/env python
# -*- coding:Utf-8 -*-

#
# Modules
#

import ConfigParser
import os
import shutil
import sys

import logging
logger = logging.getLogger( "pluzzdl" )

#
# Fonction
#

def resourcePath( relative ):
	if( getattr( sys, "frozen", None ) ):
		basedir = sys._MEIPASS
	else:
		basedir = os.path.dirname( __file__ )
	return os.path.join( basedir, relative )

#
# Classe
#

class Configuration( object ):

	def __init__( self ):
		# Les chemins sont differents selon l'OS utilise
		if( os.name == "nt" ):
			self.configDefaultFileName = resourcePath( "pluzzdl_default.cfg" )
			self.configFileName = resourcePath( "pluzzdl.cfg" )
		else:
			self.configDefaultFileName = os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "pluzzdl_default.cfg" )
			self.configFileName = os.path.join( os.path.expanduser( "~" ), ".config", "pluzzdl.cfg" )
		# Si le fichier de configuration n'est pas present dans le repertoire de l'utilisateur ou si celui par defaut est plus recent
		if( os.path.exists( self.configDefaultFileName ) and ( ( not os.path.exists( self.configFileName ) ) or ( os.path.getmtime( self.configDefaultFileName ) > os.path.getmtime( self.configFileName ) ) ) ):
			# Copie du fichier par defaut
			logger.info( "Copie du fichier de configuration par défaut" )
			try:
				shutil.copyfile( self.configDefaultFileName, self.configFileName )
			except:
				logger.error( "Impossible de copier le fichier de configuration par défaut dans le home de l'utilisateur" )
				sys.exit( 1 )
		# Verifie que le fichier de configuration existe
		if( not os.path.exists( self.configFileName ) ):
			logger.error( "Le fichier de configuration %s n'existe pas..." % ( self.configFileName ) )
			sys.exit( 1 )
		# Parser
		self.configParser = ConfigParser.RawConfigParser()
		# Options
		self.optionsDict = {}
		# Lecture de la configuration
		self.readConfig()

	def __getitem__( self, key ):
		if( self.optionsDict.has_key( key ) ):
			return self.optionsDict[ key ]
		else:
			return None

	def __setitem__( self, key, value ):
		self.optionsDict[ key ] = value

	def readConfig( self ):
		try:
			self.configParser.read( self.configFileName )
			for section in self.configParser.sections():
				for option in self.configParser.options( section ):
					self.optionsDict[ option ] = self.configParser.get( section, option )
		except:
			logger.error( "Impossible de lire le fichier de configuration" )
			sys.exit( 1 )

	def writeConfig( self ):
		try:
			# Seule l'option "player_hash" a ete modifiee
			self.configParser.set( "Keys", "player_hash", self.optionsDict[ "player_hash" ] )
			with open( self.configFileName, "wb" ) as configFile:
				self.configParser.write( configFile )
		except:
			logger.error( "Impossible d'écrire le fichier de configuration" )
