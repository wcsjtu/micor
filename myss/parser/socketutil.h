
#ifndef WIN32
#include <arpa/inet.h>
#else /* MS_WINDOWS */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <MSTcpIP.h>
#endif

#include <Python.h>

PyObject *socket_inet_ntop(int af, char* buf, int buf_len);