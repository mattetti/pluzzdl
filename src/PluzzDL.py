#!/usr/bin/env python
# -*- coding:Utf-8 -*-

# Notes :
#    -> Filtre Wireshark :
#          http.host contains "ftvodhdsecz" or http.host contains "francetv" or http.host contains "pluzz"
#    ->

#
# Modules
#

import base64
import BeautifulSoup
import binascii
import datetime
import hashlib
import hmac
import os
import re
import StringIO
import struct
import threading
import time
import urllib
import urllib2
import xml.etree.ElementTree
import xml.sax
import zlib

from Configuration import Configuration
from Historique    import Historique, Video
from Navigateur    import Navigateur

import logging
logger = logging.getLogger( "pluzzdl" )

#
# Classes
#

class PluzzDL( object ):
	"""
	Classe principale pour lancer un telechargement
	"""

	REGEX_ID = "http://info.francetelevisions.fr/\?id-video=([^\"]+)"
	XML_DESCRIPTION = "http://www.pluzz.fr/appftv/webservices/video/getInfosOeuvre.php?mode=zeri&id-diffusion=_ID_EMISSION_"
	URL_SMI = "http://www.pluzz.fr/appftv/webservices/video/getFichierSmi.php?smi=_CHAINE_/_ID_EMISSION_.smi&source=azad"
	M3U8_LINK = "http://medias2.francetv.fr/catchup-mobile/france-dom-tom/non-token/non-drm/m3u8/_FILE_NAME_.m3u8"
	REGEX_M3U8 = "/([0-9]{4}/S[0-9]{2}/J[0-9]{1}/[0-9]*-[0-9]{6,8})-"

	def __init__( self,
				  url,  # URL de la video
				  proxy = None,  # Proxy a utiliser
				  proxySock = False,  # Indique si le proxy est de type SOCK
				  sousTitres = False,  # Telechargement des sous-titres ?
				  progressFnct = lambda x : None,  # Callback pour la progression du telechargement
				  stopDownloadEvent = threading.Event(),  # Event pour arreter un telechargement
				  outDir = "."  # Repertoire de sortie de la video telechargee
				):
		# Classe pour telecharger des fichiers
		self.navigateur = Navigateur( proxy, proxySock )
		# Infos video recuperees dans le XML
		self.id = None
		self.lienMMS = None
		self.lienRTMP = None
		self.manifestURL = None
		self.m3u8URL = None
		self.drm = None
		self.chaine = None
		self.timeStamp = None
		self.codeProgramme = None

		# Recupere l'id de l'emission
		idEmission = self.getId( url )
		# Recupere la page d'infos de l'emission
		pageInfos = self.navigateur.getFichier( self.XML_DESCRIPTION.replace( "_ID_EMISSION_", idEmission ) )
		# Parse la page d'infos
		self.parseInfos( pageInfos )
		# Petit message en cas de DRM
		if( self.drm == "oui" ):
			logger.warning( "La vidéo posséde un DRM ; elle sera sans doute illisible" )
		# Verification qu'un lien existe
		if( self.m3u8URL is None and
			self.manifestURL is None and
			self.lienRTMP is None and
			self.lienMMS is None ):
			raise PluzzDLException( "Aucun lien vers la vidéo" )
		# Le telechargement se fait de differente facon selon le type du lien disponible
		# Pour l'instant, seule la methode via les liens m3u8 fonctionne
		# Le code pour les autres liens reste quand meme en place pour etre utilise si les elements manquants sont trouves (clef HMAC par exemple)
		if( self.m3u8URL is not None ):
			# Nom du fichier
			nomFichier = self.getNomFichier( outDir, self.codeProgramme, self.timeStamp, "ts" )
			# Downloader
			downloader = PluzzDLM3U8( self.m3u8URL, nomFichier, self.navigateur, stopDownloadEvent, progressFnct )
		elif( self.manifestURL is not None ):
			# Nom du fichier
			nomFichier = self.getNomFichier( outDir, self.codeProgramme, self.timeStamp, "flv" )
			# Downloader
			downloader = PluzzDLF4M( self.manifestURL, nomFichier, self.navigateur, stopDownloadEvent, progressFnct )
		elif( self.lienRTMP is not None ):
			# Downloader
			downloader = PluzzDLRTMP( self.lienRTMP )
		elif( self.lienMMS is not None ):
			# Downloader
			downloader = PluzzDLMMS( self.lienMMS )
		# Recupere les sous titres si necessaire
		if( sousTitres ):
			self.telechargerSousTitres( idEmission, self.chaine, nomFichier )
		# Lance le téléchargement
		downloader.telecharger()

	def getId( self, url ):
		"""
		Recupere l'ID de la video a partir de son URL
		"""
		#try :
		page = self.navigateur.getFichier( url )
		logger.info( page )
		idEmission = re.findall( self.REGEX_ID, page )[ 0 ]
		logger.debug( "ID de l'émission : %s" % ( idEmission ) )
		return idEmission
		#except :
			#raise PluzzDLException( "Impossible de récupérer l'ID de l'émission" )

	def parseInfos( self, pageInfos ):
		"""
		Parse le fichier de description XML d'une emission
		"""
		try :
			xml.sax.parseString( pageInfos, PluzzDLInfosHandler( self ) )
			# Si le lien m3u8 n'existe pas, il faut essayer de creer celui de la plateforme mobile
			if( self.m3u8URL is None ):
				self.m3u8URL = self.M3U8_LINK.replace( "_FILE_NAME_", re.findall( self.REGEX_M3U8, pageInfos )[ 0 ] )
			logger.debug( "URL m3u8 : %s" % ( self.m3u8URL ) )
			logger.debug( "URL manifest : %s" % ( self.manifestURL ) )
			logger.debug( "Lien RTMP : %s" % ( self.lienRTMP ) )
			logger.debug( "Lien MMS : %s" % ( self.lienMMS ) )
			logger.debug( "Utilisation de DRM : %s" % ( self.drm ) )
		except :
			raise PluzzDLException( "Impossible de parser le fichier XML de l'émission" )

	def getNomFichier( self, repertoire, codeProgramme, timeStamp, extension ):
		"""
		Construit le nom du fichier de sortie
		"""
		return os.path.join( repertoire, "%s_%s.%s" % ( codeProgramme, datetime.datetime.fromtimestamp( timeStamp ).strftime( "%Y-%m-%d_%H-%M" ), extension ) )

	def telechargerSousTitres( self, idEmission, nomChaine, nomVideo ):
		"""
		Recupere le fichier de sous titre de la video
		"""
		urlSousTitres = self.URL_SMI.replace( "_CHAINE_", nomChaine.lower().replace( " ", "" ) ).replace( "_ID_EMISSION_", idEmission )
		# Essaye de recuperer le sous titre
		try:
			sousTitresSmi = self.navigateur.getFichier( urlSousTitres )
		except:
			logger.debug( "Sous titres indisponibles" )
			return
		logger.debug( "Sous titres disponibles" )
		# Enregistre le fichier de sous titres en smi
		try :
			( nomFichierSansExtension, _ ) = os.path.splitext( nomVideo )
			# Ecrit le fichier
			with open( "%s.smi" % ( nomFichierSansExtension ), "w" ) as f:
				f.write( sousTitresSmi )
		except :
			raise PluzzDLException( "Impossible d'écrire dans le répertoire %s" % ( os.getcwd() ) )
		logger.debug( "Fichier de sous titre smi enregistré" )
		# Convertit le fichier de sous titres en srt
		try:
			with open( "%s.srt" % ( nomFichierSansExtension ), "w" ) as f:
				pageSoup = BeautifulSoup.BeautifulSoup( sousTitresSmi )
				elmts = pageSoup.findAll( "sync" )
				indice = 1
				for ( elmtDebut, elmtFin ) in ( elmts[ i : i + 2 ] for i in range( 0, len( elmts ), 2 ) ):
					# Extrait le temps de debut et le texte
					tempsEnMs = int( elmtDebut[ "start" ] )
					tempsDebutSrt = time.strftime( "%H:%M:%S,XXX", time.gmtime( int( tempsEnMs / 1000 ) ) )
					tempsDebutSrt = tempsDebutSrt.replace( "XXX", str( tempsEnMs )[ -3 : ] )
					lignes = elmtDebut.p.findAll( "span" )
					texte = "\n".join( map( lambda x : x.contents[ 0 ].strip(), lignes ) )
					# Extrait le temps de fin
					tempsEnMs = int( elmtFin[ "start" ] )
					tempsFinSrt = time.strftime( "%H:%M:%S,XXX", time.gmtime( int( tempsEnMs / 1000 ) ) )
					tempsFinSrt = tempsFinSrt.replace( "XXX", str( tempsEnMs )[ -3 : ] )
					# Ecrit dans le fichier
					f.write( "%d\n" % ( indice ) )
					f.write( "%s --> %s\n" % ( tempsDebutSrt, tempsFinSrt ) )
					f.write( "%s\n\n" % ( texte.encode( "iso-8859-1" ) ) )
					# Element suivant
					indice += 1
		except:
			logger.error( "Impossible de convertir les sous titres en str" )
			return
		logger.debug( "Fichier de sous titre srt enregistré" )


class PluzzDLException( Exception ):
	"""
	Exception levee par PluzzDL
	"""
	pass


class PluzzDLM3U8( object ):
	"""
	Telechargement des liens m3u8
	"""

	def __init__( self, m3u8URL, nomFichier, navigateur, stopDownloadEvent, progressFnct ):
		self.m3u8URL = m3u8URL
		self.nomFichier = nomFichier
		self.navigateur = navigateur
		self.stopDownloadEvent = stopDownloadEvent
		self.progressFnct = progressFnct

		self.historique = Historique()

		self.nomFichierFinal = "%s.mkv" % ( self.nomFichier[ :-3 ] )

	def ouvrirNouvelleVideo( self ):
		"""
		Creer une nouvelle video
		"""
		try :
			# Ouverture du fichier
			self.fichierVideo = open( self.nomFichier, "wb" )
		except :
			raise PluzzDLException( "Impossible d'écrire dans le répertoire %s" % ( os.getcwd() ) )
		# Ajout de l'en-tête
		# 	Fait dans creerMKV

	def ouvrirVideoExistante( self ):
		"""
		Ouvre une video existante
		"""
		try :
			# Ouverture du fichier
			self.fichierVideo = open( self.nomFichier, "a+b" )
		except :
			raise PluzzDLException( "Impossible d'écrire dans le répertoire %s" % ( os.getcwd() ) )

	def creerMKV( self ):
		"""
		Creer un mkv a partir de la video existante (cree l'en-tete de la video)
		"""
		logger.info( "Création du fichier MKV (vidéo finale); veuillez attendre quelques instants" )
		try:
			if( os.name == "nt" ):
				commande = "ffmpeg.exe -i %s -vcodec copy -acodec copy %s 1>NUL 2>NUL" % ( self.nomFichier, self.nomFichierFinal )
			else:
				commande = "ffmpeg -i %s -vcodec copy -acodec copy %s 1>/dev/null 2>/dev/null" % ( self.nomFichier, self.nomFichierFinal )
			if( os.system( commande ) == 0 ):
				os.remove( self.nomFichier )
				logger.info( "Fin !" )
			else:
				logger.warning( "Problème lors de la création du MKV avec FFmpeg ; le fichier %s est néanmoins disponible" % ( self.nomFichier ) )
		except:
			raise PluzzDLException( "Impossible de créer la vidéo finale" )

	def telecharger( self ):
		# Recupere le fichier master.m3u8
		self.m3u8 = self.navigateur.getFichier( self.m3u8URL )
		# Extrait l'URL de base pour tous les fragments
		self.urlBase = "/".join( self.m3u8URL.split( "/" )[ :-1 ] )
		# Recupere le lien avec le plus gros bitrate
		try:
			self.listeFragmentsURL = "%s/%s" % ( self.urlBase, re.findall( ".+?\.m3u8.*", self.m3u8 )[ -1 ] )
		except:
			raise PluzzDLException( "Impossible de trouver le lien vers la liste des fragments" )
		# Recupere la liste des fragments
		self.listeFragmentsPage = self.navigateur.getFichier( self.listeFragmentsURL )
		# Extrait l'URL de tous les fragments
		self.listeFragments = re.findall( ".+?\.ts", self.listeFragmentsPage )
		#
		# Creation de la video
		#
		self.premierFragment = 1
		self.telechargementFini = False
		video = self.historique.getVideo( self.listeFragmentsURL )
		# Si la video est dans l'historique
		if( video is not None ):
			# Si la video existe sur le disque
			if( os.path.exists( self.nomFichier ) or os.path.exists( self.nomFichierFinal ) ):
				if( video.finie ):
					logger.info( "La vidéo a déjà été entièrement téléchargée" )
					if( not os.path.exists( self.nomFichierFinal ) ):
						self.creerMKV()
					return
				else:
					self.ouvrirVideoExistante()
					self.premierFragment = video.fragments
					logger.info( "Reprise du téléchargement de la vidéo au fragment %d" % ( video.fragments ) )
			else:
				self.ouvrirNouvelleVideo()
				logger.info( u"Impossible de reprendre le téléchargement de la vidéo, le fichier %s n'existe pas" % ( self.nomFichier ) )
		else:  # Si la video n'est pas dans l'historique
			self.ouvrirNouvelleVideo()
		# Nombre de fragments
		self.nbFragMax = float( len( self.listeFragments ) )
		logger.debug( "Nombre de fragments : %d" % ( self.nbFragMax ) )
		# Ajout des fragments
		logger.info( "Début du téléchargement des fragments" )
		try :
			i = self.premierFragment
			while( i <= self.nbFragMax and not self.stopDownloadEvent.isSet() ):
				frag = self.navigateur.getFichier( "%s/%s" % ( self.urlBase, self.listeFragments[ i - 1 ] ) )
				self.fichierVideo.write( frag )
				# Affichage de la progression
				self.progressFnct( min( int( ( i / self.nbFragMax ) * 100 ), 100 ) )
				i += 1
			if( i == self.nbFragMax + 1 ):
				self.progressFnct( 100 )
				self.telechargementFini = True
				logger.info( "Fin du téléchargement" )
				self.creerMKV()
		except KeyboardInterrupt:
			logger.info( "Interruption clavier" )
		except:
			logger.critical( "Erreur inconnue" )
		finally :
			# Ajout dans l'historique
			self.historique.ajouter( Video( lien = self.listeFragmentsURL, fragments = i, finie = self.telechargementFini ) )
			# Fermeture du fichier
			self.fichierVideo.close()


class PluzzDLF4M( object ):
	"""
	Telechargement des liens f4m
	"""

	adobePlayer = "http://fpdownload.adobe.com/strobe/FlashMediaPlayback_101.swf"

	def __init__( self, manifestURL, nomFichier, navigateur, stopDownloadEvent, progressFnct ):
		self.manifestURL = manifestURL
		self.nomFichier = nomFichier
		self.navigateur = navigateur
		self.stopDownloadEvent = stopDownloadEvent
		self.progressFnct = progressFnct

		self.historique = Historique()
		self.configuration = Configuration()
		self.hmacKey = self.configuration[ "hmac_key" ].decode( "hex" )
		self.playerHash = self.configuration[ "player_hash" ]

	def parseManifest( self ):
		"""
		Parse le manifest
		"""
		try :
			arbre = xml.etree.ElementTree.fromstring( self.manifest )
			# Duree
			self.duree = float( arbre.find( "{http://ns.adobe.com/f4m/1.0}duration" ).text )
			self.pv2 = arbre.find( "{http://ns.adobe.com/f4m/1.0}pv-2.0" ).text
			media = arbre.findall( "{http://ns.adobe.com/f4m/1.0}media" )[ -1 ]
			# Bitrate
			self.bitrate = int( media.attrib[ "bitrate" ] )
			# URL des fragments
			urlbootstrap = media.attrib[ "url" ]
			self.urlFrag = "%s%sSeg1-Frag" % ( self.manifestURLToken[ : self.manifestURLToken.find( "manifest.f4m" ) ], urlbootstrap )
			# Header du fichier final
			self.flvHeader = base64.b64decode( media.find( "{http://ns.adobe.com/f4m/1.0}metadata" ).text )
		except :
			raise PluzzDLException( "Impossible de parser le manifest" )

	def ouvrirNouvelleVideo( self ):
		"""
		Creer une nouvelle video
		"""
		try :
			# Ouverture du fichier
			self.fichierVideo = open( self.nomFichier, "wb" )
		except :
			raise PluzzDLException( "Impossible d'écrire dans le répertoire %s" % ( os.getcwd() ) )
		# Ajout de l'en-tête FLV
		self.fichierVideo.write( binascii.a2b_hex( "464c56010500000009000000001200010c00000000000000" ) )
		# Ajout de l'header du fichier
		self.fichierVideo.write( self.flvHeader )
		self.fichierVideo.write( binascii.a2b_hex( "00000000" ) )  # Padding pour avoir des blocs de 8

	def ouvrirVideoExistante( self ):
		"""
		Ouvre une video existante
		"""
		try :
			# Ouverture du fichier
			self.fichierVideo = open( self.nomFichier, "a+b" )
		except :
			raise PluzzDLException( "Impossible d'écrire dans le répertoire %s" % ( os.getcwd() ) )

	def decompressSWF( self, swfData ):
		"""
		Decompresse un fichier swf
		"""
		# Adapted from :
		#    Prozacgod
		#    http://www.python-forum.org/pythonforum/viewtopic.php?f=2&t=14693
		if( type( swfData ) is str ):
			swfData = StringIO.StringIO( swfData )

		swfData.seek( 0, 0 )
		magic = swfData.read( 3 )

		if( magic == "CWS" ):
			return "FWS" + swfData.read( 5 ) + zlib.decompress( swfData.read() )
		else:
			return None

	def getPlayerHash( self ):
		"""
		Recupere le sha256 du player flash
		"""
		# Get SWF player
		playerData = self.navigateur.getFichier( "http://static.francetv.fr/players/Flash.H264/player.swf" )
		# Uncompress SWF player
		playerDataUncompress = self.decompressSWF( playerData )
		# Perform sha256 of uncompressed SWF player
		hashPlayer = hashlib.sha256( playerDataUncompress ).hexdigest()
		# Perform base64
		return base64.encodestring( hashPlayer.decode( 'hex' ) )

	def debutVideo( self, fragID, fragData ):
		"""
		Trouve le debut de la video dans un fragment
		"""
		# Skip fragment header
		start = fragData.find( "mdat" ) + 4
		# For all fragment (except frag1)
		if( fragID > 1 ):
			# Skip 2 FLV tags
			for dummy in range( 2 ):
				tagLen, = struct.unpack_from( ">L", fragData, start )  # Read 32 bits (big endian)
				tagLen &= 0x00ffffff  # Take the last 24 bits
				start += tagLen + 11 + 4  # 11 = tag header len ; 4 = tag footer len
		return start

	def telecharger( self ):
		# Verifie si le lien du manifest contient la chaine "media-secure"
		if( self.manifestURL.find( "media-secure" ) != -1 ):
			raise PluzzDLException( "pluzzdl ne sait pas gérer ce type de vidéo (utilisation de DRMs)..." )
		# Lien du manifest (apres le token)
		self.manifestURLToken = self.navigateur.getFichier( "http://hdfauth.francetv.fr/esi/urltokengen2.html?url=%s" % ( self.manifestURL[ self.manifestURL.find( "/z/" ) : ] ) )
		# Recupere le manifest
		self.manifest = self.navigateur.getFichier( self.manifestURLToken )
		# Parse le manifest
		self.parseManifest()
		# Calcul les elements
		self.hdnea = self.manifestURLToken[ self.manifestURLToken.find( "hdnea" ) : ]
		self.pv20, self.hdntl = self.pv2.split( ";" )
		self.pvtokenData = r"st=0000000000~exp=9999999999~acl=%2f%2a~data=" + self.pv20 + "!" + self.playerHash
		self.pvtoken = "pvtoken=%s~hmac=%s" % ( urllib.quote( self.pvtokenData ), hmac.new( self.hmacKey, self.pvtokenData, hashlib.sha256 ).hexdigest() )

		#
		# Creation de la video
		#
		self.premierFragment = 1
		self.telechargementFini = False

		video = self.historique.getVideo( self.urlFrag )
		# Si la video est dans l'historique
		if( video is not None ):
			# Si la video existe sur le disque
			if( os.path.exists( self.nomFichier ) ):
				if( video.finie ):
					logger.info( "La vidéo a déjà été entièrement téléchargée" )
					return
				else:
					self.ouvrirVideoExistante()
					self.premierFragment = video.fragments
					logger.info( "Reprise du téléchargement de la vidéo au fragment %d" % ( video.fragments ) )
			else:
				self.ouvrirNouvelleVideo()
				logger.info( "Impossible de reprendre le téléchargement de la vidéo, le fichier %s n'existe pas" % ( self.nomFichier ) )
		else:  # Si la video n'est pas dans l'historique
			self.ouvrirNouvelleVideo()

		# Calcul l'estimation du nombre de fragments
		self.nbFragMax = round( self.duree / 6 )
		logger.debug( "Estimation du nombre de fragments : %d" % ( self.nbFragMax ) )

		# Ajout des fragments
		logger.info( "Début du téléchargement des fragments" )
		try :
			i = self.premierFragment
			self.navigateur.appendCookie( "hdntl", self.hdntl )
			while( not self.stopDownloadEvent.isSet() ):
				# frag  = self.navigateur.getFichier( "%s%d?%s&%s&%s" %( self.urlFrag, i, self.pvtoken, self.hdntl, self.hdnea ) )
				frag = self.navigateur.getFichier( "%s%d" % ( self.urlFrag, i ), referer = self.adobePlayer )
				debut = self.debutVideo( i, frag )
				self.fichierVideo.write( frag[ debut : ] )
				# Affichage de la progression
				self.progressFnct( min( int( ( i / self.nbFragMax ) * 100 ), 100 ) )
				i += 1
		except urllib2.URLError, e :
			if( hasattr( e, 'code' ) ):
				if( e.code == 403 ):
					if( e.reason == "Forbidden" ):
						logger.info( "Le hash du player semble invalide ; calcul du nouveau hash" )
						newPlayerHash = self.getPlayerHash()
						if( newPlayerHash != self.playerHash ):
							self.configuration[ "player_hash" ] = newPlayerHash
							self.configuration.writeConfig()
							logger.info( "Un nouveau hash a été trouvé ; essayez de relancer l'application" )
						else:
							logger.critical( "Pas de nouveau hash disponible..." )
					else:
						logger.critical( "Impossible de charger la vidéo" )
				elif( e.code == 404 ):
					self.progressFnct( 100 )
					self.telechargementFini = True
					logger.info( "Fin du téléchargement" )
		except KeyboardInterrupt:
			logger.info( "Interruption clavier" )
		except:
			logger.critical( "Erreur inconnue" )
		finally :
			# Ajout dans l'historique
			self.historique.ajouter( Video( lien = self.urlFrag, fragments = i, finie = self.telechargementFini ) )
			# Fermeture du fichier
			self.fichierVideo.close()


class PluzzDLRTMP( object ):
	"""
	Telechargement des liens rtmp
	"""

	def __init__( self, lienRTMP ):
		self.lien = lienRTMP

	def telecharger( self ):
		logger.info( "Lien RTMP : %s\nUtiliser par exemple rtmpdump pour la recuperer directement" % ( self.lien ) )


class PluzzDLMMS( object ):
	"""
	Telechargement des liens mms
	"""

	def __init__( self, lienMMS ):
		self.lien = lienMMS

	def telecharger( self ):
		logger.info( "Lien MMS : %s\nUtiliser par exemple mimms ou msdl pour la recuperer directement" % ( self.lien ) )

class PluzzDLInfosHandler( xml.sax.handler.ContentHandler ):
	"""
	Handler pour parser le XML de description d'une emission
	"""

	def __init__( self, pluzzdl ):
		self.pluzzdl = pluzzdl

		self.isUrl = False
		self.isDRM = False
		self.isChaine = False
		self.isCodeProgramme = False

	def startElement( self, name, attrs ):
		if( name == "url" ):
			self.isUrl = True
		elif( name == "drm" ):
			self.isDRM = True
		elif( name == "chaine" ):
			self.isChaine = True
		elif( name == "diffusion" ):
			self.pluzzdl.timeStamp = float( attrs.getValue( "timestamp" ) )
		elif( name == "code_programme" ):
			self.isCodeProgramme = True

	def characters( self, data ):
		if( self.isUrl ):
			if( data[ : 3 ] == "mms" ):
				self.pluzzdl.lienMMS = data
			elif( data[ : 4 ] == "rtmp" ):
				self.pluzzdl.lienRTMP = data
			elif( data[ -3 : ] == "f4m" ):
				self.pluzzdl.manifestURL = data
			elif( data[ -4 : ] == "m3u8" ):
				self.pluzzdl.m3u8URL = data
		elif( self.isDRM ):
			self.pluzzdl.drm = data
		elif( self.isChaine ):
			self.pluzzdl.chaine = data
		elif( self.isCodeProgramme ):
			self.pluzzdl.codeProgramme = data

	def endElement( self, name ):
		if( name == "url" ):
			self.isUrl = False
		elif( name == "drm" ):
			self.isDRM = False
		elif( name == "chaine" ):
			self.isChaine = False
		elif( name == "code_programme" ):
			self.isCodeProgramme = False
