
#ifndef SOCKETUTIL_H
#define SOCKETUTIL_H

#ifndef WIN32
#include <arpa/inet.h>
#else /* MS_WINDOWS */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <MSTcpIP.h>
#endif

#include "mypydev.h"
PyObject *socket_inet_ntop(int af, char* buf, int buf_len);
size_t unpack(char* sd, size_t n);


void packs(unsigned char* buf, unsigned short v);
void packl(unsigned char* buf, unsigned int v);
void packll(unsigned char* buf, unsigned long long v);

#endif