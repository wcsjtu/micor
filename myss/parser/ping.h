#ifndef _PING_H
#define _PING_H

#include "mypydev.h"
#include "socketutil.h"

#ifndef WIN32
#include <arpa/inet.h>
#else /* MS_WINDOWS */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <MSTcpIP.h>
#endif

typedef struct _iphdr{
	unsigned char vihl;			// 版本号(4)+头长度(4)
	unsigned char tos;			// 服务类型(8)
	unsigned short len;			// 总长度(16)
	unsigned short id;			// 标识(16)
	unsigned short flag_off;	// 标志(3) + 片偏移(13)
	unsigned char ttl;			// 生存时间(8)
	unsigned char protocol;		// 协议(8)
	unsigned short checksum;	// 生存时间(16)
	unsigned int src_addr;		// 源IP地址(32)
	unsigned int dst_addr;		// 目的IP地址(32)
} IPHeader, *pIPHeader;


/*
类型8， 代码0：表示回显请求(ping请求)。
类型0， 代码0：表示回显应答(ping应答)
类型11，代码0：超时
*/

typedef struct _icmphdr{
	unsigned char type;			// 类型(8)
	unsigned char code;			// 代码(8)
	unsigned short checksum;	// 校验和(16)
	unsigned short id;			// 标识(16)
	unsigned short seq;			// 序列号(16)
} ICMPHeader, *pICMPHeader;

#define ICMP_HEADER_LENGTH sizeof(ICMPHeader)
#define IP_HEADER_LENGTH sizeof(IPHeader)


#define ICMP_ECHO_REQUEST 0x08	//ping request
#define ICMP_ECHO_REPLY   0x00	//ping reply
#define ICMP_ECHO_CODE 0x00		//ping request/reply code


//Py

typedef struct _PyICMP{
	PyObject_HEAD
	unsigned char type;			// 类型(8)
	unsigned char code;			// 代码(8)
	unsigned short checksum;	// 校验和(16)
	unsigned short id;			// 标识(16)
	unsigned short seq;			// 序列号(16)
	unsigned char ip_ttl;		// ip层的生存时间
	unsigned int ip_src_addr;
	unsigned int ip_dst_addr;
	PyBytesObject* data;
} PyICMPFrame;


PyObject* PyBuild_ping_pkg(PyObject* self, PyObject* args);

PyObject* PyParse_ping_pkg(PyObject* self, PyObject* v);

PyDoc_STRVAR(bpp_doc, 
	"build_ping_pkg(data: bytes, id: int, seq: int) -> bytes\n\
	\n\
	build ICMP echo request use data and seq, return\n\
	a bytes-object\n\
	`id` is ID of ICMP headers, type is `unsigned short`\n\
	`seq` is sequence of ICMP headers, type is `unsigned short`");

PyDoc_STRVAR(ppp_doc, 
	"parse_ping_pkg(v: bytes) -> ICMPFrame instance\n\
	");


#endif