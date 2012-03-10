/*
 * rtmpdump plugin for downloading streams from the (new) YLE Areena
 *
 *      Copyright (C) 2009-2012 Antti Ajanki <antti.ajanki@iki.fi>
 *
 *  This Program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2, or (at your option)
 *  any later version.
 *
 *  This Program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with RTMPDump; see the file COPYING.  If not, write to
 *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
 *  http://www.gnu.org/copyleft/gpl.html
 *
 */

/*
 * YLE Areena has two custom features that make downloading RTMP
 * streams more complicated than downloading from a typical RTMP
 * server. When the player connects to the server, the server sends a
 * challenge and the player has to respond correctly, otherwise the
 * server refuses to talk to the player. Secondly, the name of the
 * stream (playpath) is not available on the web page as is the case
 * usually. Instead, the web page contains a clip ID, which the player
 * must send to the server. The server then responds with the real
 * playpath.
 *
 * In more detail, to access the stream the player must perform the
 * following steps after the RTMP handshake:
 *
 * Client -> Server: invoke (RTMP packet 0x14): connect()
 *
 * S -> C: invoke: authenticationDetails(..., randomAuth: 12345)
 *
 * C -> S: flex message (0x11): authenticateRandomNumber((randomAuth + 447537687) % 6834253)
 *
 * S -> C: invoke: randomNumberAuthenticated()
 *
 * C -> S: flex message: requestData("e0", "/<clipID>")
 *         where <clipID> is the value of the id property of the
 *         AREENA.clip javascript object from the Areena web page.
 *         See function RequestData().
 *
 *         Alternatively, for live streams:
 *
 * C -> S: flex message: requestData("e0", "streams/fi/<clipID>")
 *
 * S -> C: invoke: rpcResult("e0", mediaxml)
 *         where mediaxml is an XML object whose url node contains the
 *         real playpath. See function ExecuteRPCResult().
 *
 * After receiving the playpath, the player can continue downloading
 * the stream normally.
 *
 * These notes describe the new version of Yle Areena, which is in
 * public beta (http://areena-beta.yle.fi) as of Dec 2011.
 */

#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include <librtmp/log.h>
#include <librtmp/amf.h>

#include "yle.h"

#define FREE_AND_NULL(x) { if(x) { free(x); x = NULL; } }
#define STR2AVAL(av,str) { av.av_val = str; av.av_len = strlen(av.av_val); }
#define SAVC(x) static const AVal av_##x = AVC(#x)

SAVC(connect);
SAVC(authenticationDetails);
SAVC(randomNumberAuthenticated);
SAVC(rpcResult);
SAVC(rpcError);
SAVC(locatedInBroadcastTerritory);
SAVC(randomAuth);
SAVC(tvFeeActivated);
SAVC(authenticateRandomNumber);
SAVC(requestData);
SAVC(e0);

static int ConnectYLE(RTMP *r, const AVal *methodInvoked, AMFObject *obj, void *ctx);
static int ExecuteInvokedMethod(RTMP *r, const AVal *method, AMFObject *obj, void *ctx);
static int ExecuteAuthenticationDetails(RTMP *r, AMFObject *proplist, YLENGStream *yle);
static int RequestData(RTMP *r, YLENGStream *yle);
static int ExecuteRandomNumberAuthenticated(RTMP *r);
static int ExecuteRPCResult(RTMP *r, AMFObject *obj, YLENGStream *yle, int *redirected);
static char *GetXMLNodeContent(const char *xmldoc, const char *node);
static int ParseYLEPlaypath(const char *url, AVal *host, AVal *app, AVal *playpath);


int ConnectYLE(RTMP *r, const AVal *methodInvoked, AMFObject *obj, void *ctx) {
  struct YLENGStream *yle = (struct YLENGStream *)ctx;

  if (!yle || !AVMATCH(methodInvoked, &av_connect) || yle->yleAuth == 0)
    return RTMP_CB_NOT_HANDLED;

  /* Like connection handling in librtmp but don't send
     Ctrl or CreateStream. */

  RTMP_SendServerBW(r);
  /*RTMP_SendCtrl(r, 3, 0, 300);*/

  return RTMP_CB_SUCCESS;
}

int ExecuteInvokedMethod(RTMP *r, const AVal *method, AMFObject *obj, void *ctx) {
  struct YLENGStream *yle = (struct YLENGStream *)ctx;
  int redirected = FALSE;

  if (!yle || yle->yleAuth == 0)
    return RTMP_CB_NOT_HANDLED;

  if (AVMATCH(method, &av_authenticationDetails)) {
    AMFObject list;
    AMFProp_GetObject(AMF_GetProp(obj, NULL, 3), &list);
    if (!ExecuteAuthenticationDetails(r, &list, yle))
      return RTMP_CB_ERROR_STOP;
    
    if (yle->clipID.av_len) {
      if (!RequestData(r, yle))
        return RTMP_CB_ERROR_STOP;
    } else if (!RTMP_SendCreateStream(r)) {
      return RTMP_CB_ERROR_STOP;
    }
        
    return RTMP_CB_SUCCESS;

  } else if (AVMATCH(method, &av_randomNumberAuthenticated)) {
    ExecuteRandomNumberAuthenticated(r);
    return RTMP_CB_SUCCESS;

  } else if (AVMATCH(method, &av_rpcResult)) {
    if (!ExecuteRPCResult(r, obj, yle, &redirected))
      return RTMP_CB_ERROR_STOP;

    //if (redirected && !ConnectRedirected(r, r->Link.seekTime, yle))
    //  return RTMP_CB_ERROR_STOP;

    return RTMP_CB_SUCCESS;

  } else if (AVMATCH(method, &av_rpcError)) {
    RTMP_Log(RTMP_LOGERROR, "RTMP server returned RPC error");
    return RTMP_CB_ERROR_STOP;
  }

  return RTMP_CB_NOT_HANDLED;
}

int ExecuteAuthenticationDetails(RTMP *r, AMFObject *proplist, YLENGStream *yle) {
  long authResult = -1;
  int i;
  
  for (i=0; i<AMF_CountProp(proplist); i++) {
    AVal name;
    AMFObjectProperty *prop = AMF_GetProp(proplist, NULL, i);
    AMFProp_GetName(prop, &name);

    if (AVMATCH(&name, &av_locatedInBroadcastTerritory)) {
      yle->locatedInBroadcastTerritory = AMFProp_GetBoolean(prop);
    } else if (AVMATCH(&name, &av_randomAuth)) {
      authResult = ((long)AMFProp_GetNumber(prop) + 447537687) % 6834253;
    } else if (AVMATCH(&name, &av_tvFeeActivated)) {
      yle->tvFeeActivated = AMFProp_GetBoolean(prop);
    }
  }

  if (authResult != -1) {
    RTMPPacket packet;
    char pbuf[128], *pend = pbuf+sizeof(pbuf);

    packet.m_nChannel = 0x03;   // control channel
    packet.m_headerType = RTMP_PACKET_SIZE_LARGE;
    packet.m_packetType = 0x11; // FLEX MESSAGE
    packet.m_nTimeStamp = RTMP_GetTime();
    packet.m_nInfoField2 = 0;
    packet.m_hasAbsTimestamp = 0;

    packet.m_body = pbuf + RTMP_MAX_HEADER_SIZE;
    char *enc = packet.m_body;
    *enc++ = 0x00;   // Unknown
    enc = AMF_EncodeString(enc, pend, &av_authenticateRandomNumber);
    enc = AMF_EncodeNumber(enc, pend, 0);
    *enc++ = AMF_NULL;
    enc = AMF_EncodeNumber(enc, pend, (double)authResult);

    packet.m_nBodySize = enc-packet.m_body;

    RTMP_Log(RTMP_LOGDEBUG, "sending authenticateRandomNumber");

    return RTMP_SendPacket(r, &packet, FALSE);
  }

  return FALSE;
}

int RequestData(RTMP *r, YLENGStream *yle) {
  RTMPPacket packet;
  char pbuf[128], *pend = pbuf+sizeof(pbuf);
  AVal clipID;

  packet.m_nChannel = 0x03;   // control channel
  packet.m_headerType = RTMP_PACKET_SIZE_LARGE;
  packet.m_packetType = 0x11; // FLEX MESSAGE
  packet.m_nTimeStamp = RTMP_GetTime();
  packet.m_nInfoField2 = 0;
  packet.m_hasAbsTimestamp = 0;

  packet.m_body = pbuf + RTMP_MAX_HEADER_SIZE;
  char *enc = packet.m_body;
  *enc++ = 0x00;   // Unknown
  enc = AMF_EncodeString(enc, pend, &av_requestData);
  enc = AMF_EncodeNumber(enc, pend, 0);
  *enc++ = AMF_NULL;
  enc = AMF_EncodeString(enc, pend, &av_e0);

  if ((r->Link.lFlags & RTMP_LF_LIVE) != 0) {
    char *tmp = malloc(yle->clipID.av_len+12);
    strcpy(tmp, "streams/fi/");
    strncat(tmp, yle->clipID.av_val, yle->clipID.av_len);
    STR2AVAL(clipID, tmp);
    enc = AMF_EncodeString(enc, pend, &clipID);
    free(tmp);
  } else {
    char *tmp = malloc(yle->clipID.av_len+2);
    strcpy(tmp, "/");
    strncat(tmp, yle->clipID.av_val, yle->clipID.av_len);
    STR2AVAL(clipID, tmp);
    enc = AMF_EncodeString(enc, pend, &clipID);
    free(tmp);
  }

  if (!enc) {
    RTMP_Log(RTMP_LOGERROR, "Buffer too short in RequestData");
    return FALSE;
  }

  packet.m_nBodySize = enc-packet.m_body;

  return RTMP_SendPacket(r, &packet, FALSE);
}

int ExecuteRandomNumberAuthenticated(RTMP *r) {
  // do nothing
  return TRUE;
}

int ExecuteRPCResult(RTMP *r, AMFObject *obj, YLENGStream *yle, int *redirected) {
  AVal rpcKind;
  AVal mediaxml;
  char *playurl, *tvpayOnly;
  AVal parsedHost = {NULL, 0};
  AVal parsedPlaypath = {NULL, 0};
  AVal parsedApp = {NULL, 0};

  *redirected = FALSE;

  AMFProp_GetString(AMF_GetProp(obj, NULL, 3), &rpcKind);
  
  if (!AVMATCH(&rpcKind, &av_e0))
    return TRUE;

  AMFProp_GetString(AMF_GetProp(obj, NULL, 4), &mediaxml);
  RTMP_Log(RTMP_LOGDEBUG, "clip data:\n%.*s", mediaxml.av_len, mediaxml.av_val);

  playurl = GetXMLNodeContent(mediaxml.av_val, "url");
  if (!playurl)
    return FALSE;

  if (!ParseYLEPlaypath(playurl, &parsedHost, &parsedApp, &parsedPlaypath)) {
    RTMP_Log(RTMP_LOGERROR, "Couldn't parse stream url %s!", playurl);
    free(playurl);
    return FALSE;
  }

  // FIXME: old r->Link.playpath may be leaked
  r->Link.playpath.av_len = parsedPlaypath.av_len;
  r->Link.playpath.av_val = malloc(parsedPlaypath.av_len*sizeof(char));
  strncpy(r->Link.playpath.av_val, parsedPlaypath.av_val, r->Link.playpath.av_len);

  RTMP_Log(RTMP_LOGDEBUG, "New playpath   : %.*s",
           r->Link.playpath.av_len, r->Link.playpath.av_val);

  if (!AVMATCH(&parsedHost, &r->Link.hostname)) {
    RTMP_Log(RTMP_LOGDEBUG, "Redirected to another server: %.*s",
             parsedHost.av_len, parsedHost.av_val);

    // FIXME: old value may be leaked
    r->Link.hostname.av_val = malloc(parsedHost.av_len*sizeof(char));
    r->Link.hostname.av_len = parsedHost.av_len;
    memcpy(r->Link.hostname.av_val, parsedHost.av_val, parsedHost.av_len);

    *redirected = TRUE;
  }

  tvpayOnly = GetXMLNodeContent(mediaxml.av_val, "tvpayOnly");
  if (tvpayOnly) {
    yle->tvFeeRequired = (strcmp(tvpayOnly, "false")!=0);
    free(tvpayOnly);
  }

  free(playurl);

  return RTMP_SendCreateStream(r);
}

/*
 * Special playpath parsing which is adjusted for YLE RTMP URLs.
 *
 * In YLE playpaths, app is just one component long and the playpath
 * already includes mp4: or mp3: prefix and the extension when needed.
 */
int ParseYLEPlaypath(const char *url, AVal *host, AVal *app, AVal *playpath) {
  char *p, *slash;

  p = strstr(url, "://");
  if(!p)
    return FALSE;

  // host
  p+=3;
  slash = strchr(p, '/');
  if (!slash)
    return FALSE;

  host->av_val = p;
  host->av_len = slash - p;

  // app
  p = slash+1;
  slash = strchr(p, '/');
  if (!slash)
    return FALSE;

  app->av_val = p;
  app->av_len = slash-p;

  // playpath
  p = slash+1;
  playpath->av_val = p;
  playpath->av_len = strlen(p);

  return TRUE;
}

char *GetXMLNodeContent(const char *xmldoc, const char *node) {
  char *p, *pend;
  size_t contentlen;

  if (!xmldoc)
    return NULL;

  char *node2 = malloc(strlen(node)+2);
  strcpy(node2, "<");
  strcat(node2, node);

  p = strstr(xmldoc, node2);
  if (p) {
    p += strlen(node2);

    /* Skip attributes */
    p = strchr(p, '>');
    if (p) {
      p++;
      pend = strchr(p, '<');
      if (pend) {
        contentlen = pend-p;
        
        char *ret = malloc(contentlen+1);
        strncpy(ret, p, contentlen);
        ret[contentlen] = '\0';

        p = ret;
        while ((p = strstr(p, "&amp;"))) {
          size_t len = strlen(p+5);
          p = memmove(p+1, p+5, len);
          p[len] = '\0';
        }

        free(node2);
        return ret;
      }
    }
  }

  free(node2);
  return NULL;
}

static void ParseOption(const AVal *opt, const AVal *arg, void *ctx)
{
  YLENGStream *yle = ctx;
  if (!yle)
    return;
  
  if (opt->av_len == 3 && strcasecmp(opt->av_val, "yle") == 0) {
    yle->clipID = *arg;
    yle->yleAuth = 1;
  } else if (opt->av_len == 7 && strcasecmp(opt->av_val, "yleauth") == 0) {
    yle->yleAuth = strtol(arg->av_val, NULL, 0);
  }
}

static void *NewInstance(RTMP *r) {
  YLENGStream *yle = malloc(sizeof(struct YLENGStream));
  if(!yle)
    return NULL;

  memset(yle, 0, sizeof(struct YLENGStream));

  yle->connectCBHandle =
    RTMP_AttachCallback(r, RTMP_CALLBACK_RESULT,
                        (void(*)(void))ConnectYLE, yle);
  yle->RPC_CBHandle =
    RTMP_AttachCallback(r, RTMP_CALLBACK_INVOKE,
                        (void(*)(void))ExecuteInvokedMethod, yle);

  return yle;
}

static void FreeInstance(RTMP *r, void *data) {
  YLENGStream *yle = data;
  if (!yle)
    return;

  RTMP_DetachCallback(r, yle->connectCBHandle);
  RTMP_DetachCallback(r, yle->RPC_CBHandle);
  free(yle);
}
