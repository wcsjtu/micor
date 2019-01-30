#include "sock5.h"
#include "cares.h"

//atyp
#define ATYP_IPV4 1
#define ATYP_HOST 3
#define ATYP_IPV6 4


//customed
#define SOCK_HEADER_HOST_MIN_LEN 5
#define SOCK_HEADER_IPV4_LEN 7
#define SOCK_HEADER_IPV6_LEN 19
#define IPV4_BYTES 4
#define IPV6_BYTES 16

PyObject*
SocksHeader_New(PyTypeObject *type, PyObject *args, PyObject *kwds){
	SocksHeader* self = (SocksHeader*)type->tp_alloc(type, 0);
	if (self == NULL){
		return (PyObject*)self;
	}

	self->atyp = 0;
	self->header_length = 0;
	self->dest_port = 0;
	self->dest_addr = (PyBytesObject*)PyBytes_FromString("");
	return (PyObject*)self;
}

int
SocksHeader_init(SocksHeader*self, PyObject *args, PyObject *kwds){
	PyObject* addr = NULL, *tmp = NULL;
	if (!PyArg_ParseTuple(args, "HSHI",
		&self->atyp, &addr, self->dest_port,
		self->header_length)){
		return -1;
	}

	if (addr){
		tmp = (PyObject*)self->dest_addr;
		Py_INCREF(addr);
		self->dest_addr = (PyBytesObject*)addr;
		Py_DECREF(tmp);
	}
	return 0;
}

void
SocksHeader_dealloc(SocksHeader* self){
	Py_XDECREF(self->dest_addr);
	Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject* _ClassAttrs(){
	PyObject* d = PyDict_New();
	PyDict_SetItem(d, PyUnicode_FromString("ATYP_IPV4"), PyLong_FromLong(ATYP_IPV4));
	PyDict_SetItem(d, PyUnicode_FromString("ATYP_HOST"), PyLong_FromLong(ATYP_HOST));
	PyDict_SetItem(d, PyUnicode_FromString("ATYP_IPV6"), PyLong_FromLong(ATYP_IPV6));
	return d;
}

static PyMemberDef members[] = {
	{ "atyp", T_USHORT, offsetof(SocksHeader, atyp), 0, atyp_doc },
	{ "dest_addr", T_OBJECT_EX, offsetof(SocksHeader, dest_addr), 0, addr_doc },
	{ "dest_port", T_USHORT, offsetof(SocksHeader, dest_port), 0, port_doc },
	{ "header_length", T_INT, offsetof(SocksHeader, header_length), 0, header_length_doc },
	{ NULL }
};

PyTypeObject SocksHeaderType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"cares.SocksHeader",			//tp_name,
	sizeof(SocksHeader),			//tp_basicsize
	0,								//tp_itemsize
	(destructor)SocksHeader_dealloc,//tp_dealloc
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
	SockHeader_doc,					//tp_doc
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
	_ClassAttrs(),					//tp_dict
	0,								//tp_descr_get
	0,								//tp_descr_set
	0,								//tp_dictoffset
	(initproc)SocksHeader_init,		//tp_init
	0,								//tp_alloc
	SocksHeader_New					//tp_new
};

PyObject*
parse_socks5_header(PyObject* self, PyObject* op){
	if (!PyBytes_Check(op)){
		PyErr_SetString(PyExc_TypeError, "a bytes object is required");
		return NULL;
	}
	unsigned int size = ((PyBytesObject*)op)->ob_base.ob_size;
	int length = 0;
	unsigned short int atyp = 0, port = 0;
	unsigned char addrlen = 0;
	PyObject* addr = Py_None;

	SocksHeader* sh = (SocksHeader*)SocksHeader_New(&SocksHeaderType, NULL, NULL);
	if (sh == NULL){
		return NULL;
	}

	char* data = (((PyBytesObject*)op)->ob_sval);
	if (size < SOCK_HEADER_HOST_MIN_LEN){
		length = size - SOCK_HEADER_HOST_MIN_LEN;
		goto ret;	//need more data
	}

	atyp = (unsigned short int)data[0];
	switch (atyp){
	case ATYP_IPV4:
		if (size < SOCK_HEADER_IPV4_LEN){
			length = size - SOCK_HEADER_IPV4_LEN;
			break;
		}
		addr = socket_inet_ntop(AF_INET, data+1, 4);
		if (addr == NULL)
			return NULL;
		port = unpack(data + 5, 2);
		length = SOCK_HEADER_IPV4_LEN;
		break;
	case ATYP_IPV6:
		if (size < SOCK_HEADER_IPV6_LEN){
			length = size - SOCK_HEADER_IPV6_LEN;
			break;
		}
		addr = socket_inet_ntop(AF_INET6, data + 1, 16);
		if (addr == NULL)
			return NULL;
		port = unpack(data + 17, 2);
		length = SOCK_HEADER_IPV6_LEN;
		break;
	case ATYP_HOST:
		addrlen = (unsigned char)data[1];
		if (size < ((unsigned int)2 + addrlen)){
			length = size - (4 + addrlen);	//\x03\n\www.jd.com\x00P
			break;
		}
		addr = PyBytes_FromStringAndSize(data+2, addrlen);
		if (addr == NULL)
			return NULL;
		port = unpack(data + 2 + addrlen, 2);
		length = 4 + addrlen;
		break;
	default:
		PyErr_SetString(PyExc_ValueError, "invalid qtyp");
		return NULL;
	}
	
	
ret:
	sh->atyp = atyp;
	sh->dest_addr = (PyBytesObject*)addr;
	sh->dest_port = port;
	sh->header_length = length;
	Py_INCREF(sh);
	return (PyObject*)sh;
}