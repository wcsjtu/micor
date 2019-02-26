#ifndef MAIN_H
#define MAIN_H

#include "rc4.h"
#include "mypydev.h"
#include "cares.h"
#include "sock5.h"
#include "socketutil.h"
#include "ping.h"

extern PyTypeObject DNSParserType, SocksHeaderType, RRType;
extern PyTypeObject PyICMPFrameType;


#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif

#endif