#include "cares.h"
#include "ping.h"

#define BINSUM(sum, ptr, sz) {\
	unsigned int nleft = sz; \
	unsigned short* usiptr = (unsigned short*)ptr; \
	while (nleft > 1){\
		sum += *(usiptr++);\
		nleft -= 2; \
	}\
	if (nleft == 1)\
		sum += *(unsigned char*)usiptr;\
}

static unsigned short 
calc_checksum(ICMPHeader* p_icmphdr, unsigned char* data, unsigned int size){
	p_icmphdr->checksum = 0;
	unsigned long sum = 0xffff;

	BINSUM(sum, p_icmphdr, ICMP_HEADER_LENGTH);
	BINSUM(sum, data, size);

	sum = (sum & 0xffff) + (sum >> 16);
	sum = (sum & 0xffff) + (sum >> 16);
	return (unsigned short)~sum;
}

static unsigned short
calc_checksum(IPHeader* pIPhdr){
	pIPhdr->checksum = 0;
	unsigned long sum = 0xffff;
	BINSUM(sum, pIPhdr, IP_HEADER_LENGTH);
	sum = (sum & 0xffff) + (sum >> 16);
	sum = (sum & 0xffff) + (sum >> 16);
	return (unsigned short)~sum;
}

static ICMPHeader* 
build_ping_header(unsigned short id, unsigned short seq, unsigned char* data, unsigned int datasz){
	ICMPHeader* phdr = (ICMPHeader*)malloc(ICMP_HEADER_LENGTH);
	if (phdr == NULL){
		return NULL;
	}
	phdr->code = ICMP_ECHO_CODE;
	phdr->seq = htons( seq);
	phdr->id = htons(id);
	phdr->type = ICMP_ECHO_REQUEST;
	phdr->checksum = calc_checksum(phdr, data, datasz);
	return phdr;
}

PyObject* PyBuild_ping_pkg(PyObject* self, PyObject* args){
	unsigned short seq = 0, id = 0;
	PyObject* data = NULL;

	if (!PyArg_ParseTuple(args, "SHH", &data, &id, &seq)){
		return NULL;
	}
	PyBytesObject* bd = (PyBytesObject*)data;
	ICMPHeader* pheader = build_ping_header(id, seq,
		(unsigned char*)bd->ob_sval, bd->ob_base.ob_size);
	if (pheader == NULL){
		return NULL;
	}

	size_t pkglen = ICMP_HEADER_LENGTH + bd->ob_base.ob_size;
	PyObject* res = PyBytes_FromSize(pkglen, 1);
	unsigned char* pkg = (unsigned char*)(((PyBytesObject*)res)->ob_sval);

	*pkg = pheader->type;
	*(pkg + 1) = pheader->code;
	memcpy(pkg + 2, (unsigned char*)(&(pheader->checksum)), 2);
	memcpy(pkg + 4, (unsigned char*)(&(pheader->id)), 2);
	memcpy(pkg + 6, (unsigned char*)(&(pheader->seq)), 2);
	memcpy(pkg + 8, (unsigned char*)bd->ob_sval, bd->ob_base.ob_size);

	free(pheader);
	pheader = NULL;
	return res;
}

//py

static PyObject*
ICMPFrame_New(PyTypeObject* type, PyObject *args, PyObject *kwds){
	PyICMPFrame* self = (PyICMPFrame*)type->tp_alloc(type, 0);
	if (self == NULL)
		return (PyObject*)self;

	self->checksum = 0;
	self->code = 0;
	self->id = 0;
	self->seq = 0;
	self->type = 0;
	self->ip_ttl = 0;
	self->ip_dst_addr = 0;
	self->ip_src_addr = 0;
	self->data = (PyBytesObject*)PyBytes_FromString("");
	return (PyObject*)self;
}

static void ICMPFrame_dealloc(PyICMPFrame* self){
	Py_XDECREF(self->data);
	Py_TYPE(self)->tp_free((PyObject*)self);
}

PyDoc_STRVAR(PyICMP_doc, 
	"frame struction of ICMP is\n\
	\n\
	0        7        15       23       31\n\n\
	+--------+--------+--------+--------+\n\n\
	|  type  |  code  |     checksum    |\n\n\
	+--------+--------+--------+--------+\n\n\
	|       ID        |     sequence    |\n\n\
	+--------+--------+--------+--------+\n\n\
	|           DATA(optional)          |\n\n\
	+--------+--------+--------+--------+");


static PyMemberDef members[] = {
	{ "type", T_UBYTE, offsetof(PyICMPFrame, type), 0, "type of ICMP"},
	{ "code", T_UBYTE, offsetof(PyICMPFrame, code), 0, "code of ICMP" },
	{ "checksum", T_USHORT, offsetof(PyICMPFrame, checksum), 0, "checksum of ICMP" },
	{ "id", T_USHORT, offsetof(PyICMPFrame, id), 0, "id of ICMP"},
	{ "seq", T_USHORT, offsetof(PyICMPFrame, seq), 0, "sequence of ICMP" },
	{ "ip_ttl", T_UBYTE, offsetof(PyICMPFrame, ip_ttl), 0, "TTL of IP" },
	{ "ip_src_addr", T_UINT, offsetof(PyICMPFrame, ip_src_addr), 0, "source address of IP" },
	{ "ip_dst_addr", T_UINT, offsetof(PyICMPFrame, ip_dst_addr), 0, "destination address of IP" },
	{ "data", T_OBJECT_EX, offsetof(PyICMPFrame, data), 0, "payload of ICMP" },
	{ NULL }
};

PyTypeObject PyICMPFrameType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"cares.ICMPFrame",				//tp_name,
	sizeof(PyICMPFrame),			//tp_basicsize
	0,								//tp_itemsize
	(destructor)ICMPFrame_dealloc,//tp_dealloc
	0,								//tp_print
	0,								//tp_getattr
	0,								//tp_setattr
	0,								//tp_as_async
	0,								//tp_repr
	0,								//tp_as_number
	0,								//tp_as_sequence
	0,								//tp_as_mapping
	0,								//tp_hash
	0,								//tp_call
	0,								//tp_str,
	0,								//tp_getattro
	0,								//tp_setattro
	0,								//tp_as_buffer
	Py_TPFLAGS_DEFAULT,				//tp_flags
	PyICMP_doc,						//tp_doc
	0,								//tp_traverse
	0,								//tp_clear
	0,								//tp_richcompare
	0,								//tp_weaklistoffset
	0,								//tp_iter
	0,								//tp_iternext
	0,								//tp_methods
	members,						//tp_members
	0,								//tp_getset
	0,								//tp_base
	0,								//tp_dict
	0,								//tp_descr_get
	0,								//tp_descr_set
	0,								//tp_dictoffset
	NULL,							//tp_init
	0,								//tp_alloc
	ICMPFrame_New					//tp_new
};

PyObject* PyParse_ping_pkg(PyObject* self, PyObject* v){
	if (!PyBytes_Check(v)){
		PyErr_SetString(PyExc_TypeError, "a bytes object is required");
		return NULL;
	}
	//printf("ICMP_HEADER_LENGTH = %d    IP_HEADER_LENGTH = %d\n", ICMP_HEADER_LENGTH, IP_HEADER_LENGTH);
	int nleft = ((PyBytesObject*)v)->ob_base.ob_size - ICMP_HEADER_LENGTH - IP_HEADER_LENGTH;
	char* buf = ((PyBytesObject*)v)->ob_sval + IP_HEADER_LENGTH;
	ICMPHeader* icmpheader = (ICMPHeader*)buf;
	IPHeader* ipheader = (IPHeader*)(((PyBytesObject*)v)->ob_sval);
	if (nleft < 0){
		PyErr_SetString(PyExc_ValueError, "parameter is too short");
		return NULL;
	}
	PyICMPFrame* frame = (PyICMPFrame*)ICMPFrame_New(&PyICMPFrameType, NULL, NULL);
	if (frame == NULL){
		return NULL;
	}
	frame->type = icmpheader->type;
	frame->code = icmpheader->code;
	frame->checksum = ntohs(icmpheader->checksum);
	frame->id = ntohs(icmpheader->id);
	frame->seq = ntohs(icmpheader->seq);
	frame->ip_ttl = ipheader->ttl;
	frame->ip_dst_addr = ntohl(ipheader->dst_addr);
	frame->ip_src_addr = ntohl(ipheader->src_addr);

	if (nleft > 0){
		
		PyBytesObject* data = (PyBytesObject*)PyBytes_FromSize(nleft, 1);
		if (data == NULL){
			ICMPFrame_dealloc((PyICMPFrame*)self);
			return NULL;
		}
		memcpy(data->ob_sval, buf + 8, nleft);
		frame->data = data;
	}
	Py_INCREF(frame);
	return (PyObject*)frame;
}