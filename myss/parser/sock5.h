#ifndef SOCKS5_H
#define SOCKS5_H

#include "socketutil.h"
#include "mypydev.h"

typedef struct _SocksHeader {
	PyObject_HEAD
	unsigned short int atyp;
	PyBytesObject* dest_addr;
	unsigned short int dest_port;
	int header_length;
} SocksHeader;

PyObject* 
SocksHeader_New(PyTypeObject *type, PyObject *args, PyObject *kwds);

int 
SocksHeader_init(SocksHeader* self, PyObject *args, PyObject *kwds);

void
SocksHeader_dealloc(SocksHeader* self);



//从socks5 头中解析出目标的信息, 返回一个SocksHeader类实例
PyObject*
parse_socks5_header(PyObject* self, PyObject* data);



//class def

PyDoc_STRVAR(atyp_doc, "flag which indicate the type of addr");
PyDoc_STRVAR(addr_doc, "address of destination, may be ipv4 address\n\
	or ipv6 address or hostname. type is bytes");
PyDoc_STRVAR(port_doc, "tcp/udp port of destination");
PyDoc_STRVAR(header_length_doc, "total length of socks5 header");


PyDoc_STRVAR(SockHeader_doc,
	"SocksHeader(atyp: int, dest_addr: bytes, \
	dest_port: int, header_length: int) -> SocksHeader Object\n\
	\n\
	Type which story the info cantains in socks5's header");

PyDoc_STRVAR(parse_socks5_header_doc,
	"parse_socks5_header(s: bytes) -> SocksHeader Object\n\
	\n\
	Parse destination addr and port from socks5 header. normally,\n\
	a SocksHeader instance with positive `header_length` returned, \n\
	means parse succeed; otherwise, an instance with nagetive or zero \n\
	`header_length` returned means need more data, which size === \n\
	abs(header_length). If parse failed, an exception will be raised");

#endif