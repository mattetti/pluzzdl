#!/usr/bin/env python2
# -*- coding:Utf-8 -*-

#
# Modules
#

import cPickle as pickle
import datetime
import os

import logging
logger = logging.getLogger( "pluzzdl" )

#
# Classes
#

class Video( object ):

	def __init__( self, lien, fragments, finie, date = datetime.datetime.now() ):
		self.lien = lien
		self.fragments = fragments
		self.finie = finie
		self.date = date

	def __eq__( self, other ):
		if not isinstance( other, Video ):
			return False
		else:
			return ( self.lien == other.lien )

	def __ne__( self, other ):
		return not self.__eq__( other )

class Historique( object ):

	def __init__( self ):
		# Le chemin du fichier d'historique est different selon l'OS utilise
		if( os.name == "nt" ):
			self.fichierCache = "pluzzdl.cache"
		else:
			dossierCache = os.path.join( os.path.expanduser( "~" ), ".cache" )
			if( not os.path.exists( dossierCache ) ):
				logger.info( "Création du dossier %s" % ( dossierCache ) )
				try:
					os.makedirs( dossierCache )
				except:
					logger.warning( "Impossible de créer le dossier %s" % ( dossierCache ) )
			self.fichierCache = os.path.join( dossierCache, "pluzzdl" )

		self.charger()

	def __del__( self ):
		self.sauver()

	def charger( self ):
		if( os.path.exists( self.fichierCache ) ):
			try:
				with open( self.fichierCache, "r" ) as fichier:
					self.historique = pickle.load( fichier )
					logger.debug( "Historique chargé" )
			except:
				self.historique = []
				logger.warning( "Impossible de lire le fichier d'historique %s, création d'un nouveau fichier" % ( self.fichierCache ) )
		else:
			self.historique = []
			logger.info( "Fichier d'historique indisponible, création d'un nouveau fichier" )

	def sauver( self ):
		self.nettoyer()
		try:
			with open( self.fichierCache, "w" ) as fichier:
				pickle.dump( self.historique, fichier )
				logger.debug( "Historique sauvé" )
		except:
			logger.warning( "Impossible d'écrire le fichier d'historique %s" % ( self.fichierCache ) )

	def nettoyer( self ):
		# Supprimer les videos de plus de 10 jours de l'historique
		for i in range( len( self.historique ) - 1, 0, -1 ):
			if( ( datetime.datetime.now() - self.historique[ i ].date ) > datetime.timedelta( days = 10 ) ):
				del self.historique[ i ]

	def ajouter( self, video ):
		if( isinstance( video, Video ) ):
			if( video in self.historique ):
				self.historique[ self.historique.index( video ) ] = video
			else:
				self.historique.append( video )

	def getVideo( self, lienVideo ):
		video = None
		for v in self.historique:
			if( v.lien == lienVideo ):
				video = v
				break
		return video
