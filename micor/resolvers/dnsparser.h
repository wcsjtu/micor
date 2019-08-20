#ifndef _DNSPARSER_H
#define _DNSPARSER_H

#include "Python.h"
#include "structmember.h"


#ifndef WIN32
#include <arpa/inet.h>
#else /* MS_WINDOWS */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <MSTcpIP.h>
#endif

typedef struct _RR{
	PyObject_HEAD
	PyBytesObject* domain_name;
	PyBytesObject* value;
	unsigned short qtype;
	unsigned short qcls;
	unsigned int ttl;
}RR;

typedef struct _DNSParser{
	PyObject_HEAD
	PyBytesObject* data;
	unsigned int offset;
} DNSParser;

PyObject * PyBytes_FromSize(Py_ssize_t size, int use_calloc);
PyObject *socket_inet_ntop(int af, char* buf, int buf_len);

unsigned short unpacks(char* buf);
unsigned int unpacki(char* buf);

#define PyBytesObject_SIZE (offsetof(PyBytesObject, ob_sval) + 1)

#define GET_BYTE(b, i) ( (unsigned char)(*(b->ob_sval + i)) )	//从PyBytesObject中取出byte

#define DOMAIN_END 0x00
#define DNS_REQ_HEADER_LEN 12
#define DNS_REQ_TAIL_LEN 5
#define MAX_DNS_PART_LEN 63

#define QTYPE_A 1
#define QTYPE_NS 2
#define QTYPE_CNAME 5
#define QTYPE_AAAA 28
#define QTYPE_ANY 255
#define QCLASS_IN 1

#define DNS_REQ_SIZE(domain_len) (DNS_REQ_HEADER_LEN + \
	DNS_REQ_TAIL_LEN + (domain_len) + 1)	//n个点对应着n+1段的长度, 再加上\x00结束符

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif

#endif