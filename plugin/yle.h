#ifndef __YLE_H__
#define __YLE_H__
/*
 * rtmpdump plugin for downloading streams from the (new) YLE Areena
 *
 *      Copyright (C) 2011 Antti Ajanki <antti.ajanki@iki.fi>
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

#include <librtmp/plugin.h>
#include <librtmp/rtmp.h>

typedef struct YLENGStream {
  int yleAuth;
  AVal clipID;
  int tvFeeRequired;
  int tvFeeActivated;
  int locatedInBroadcastTerritory;
  RTMPCallbackHandle connectCBHandle;
  RTMPCallbackHandle RPC_CBHandle;
} YLENGStream;

static void *NewInstance(RTMP *r);
static void FreeInstance(RTMP *r, void *data);
static void ParseOption(const AVal *opt, const AVal *arg, void *ctx);

static RTMPPluginOption yleoptions[] = 
  { {"yle", "string", "YLE Areena clip ID", ParseOption},
    {"yleauth", "int", "Enable Yle authentication (YleX Areena)", ParseOption},
    {NULL, 0, 0, NULL} };

RTMP_Plugin plugin = 
{
  0,
  "Yle Areena",
  "1.0",
  "Antti Ajanki <antti.ajanki@iki.fi>",
  "http://iki.fi/aoa/rtmpdump-yle/",
  yleoptions,
  NewInstance,
  FreeInstance
};

RTMP_PLUGIN_REGISTER(plugin);

#endif
