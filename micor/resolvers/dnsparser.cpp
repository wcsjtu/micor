#include "dnsparser.h"

// RR define

void RR_dealloc(RR* self){
	Py_XDECREF(self->domain_name);
	Py_XDECREF(self->value);
	Py_TYPE(self)->tp_free((PyObject*)self);
}

int RR_init(RR*self, PyObject *args, PyObject *kwds){
	PyObject* dn = NULL, *val = NULL, *tmp;
	if (!PyArg_ParseTuple(args, "SSHHH", &dn, &val, &self->qtype, &self->qcls, &self->ttl)){
		return -1;
	}

	if (dn){
		tmp = (PyObject*)self->domain_name;
		Py_INCREF(dn);
		self->domain_name = (PyBytesObject*)dn;
		Py_XDECREF(tmp);
	}

	if (val){
		tmp = (PyObject*)self->value;
		Py_INCREF(val);
		self->value = (PyBytesObject*)val;
		Py_XDECREF(tmp);
	}
	return 0;
}

PyObject*
RR_new(PyTypeObject *type, PyObject *args, PyObject *kwds){
	RR* self;
	self = (RR*)type->tp_alloc(type, 0);
	if (self != NULL){
		self->domain_name = (PyBytesObject*)PyBytes_FromString("");
		if (self->domain_name == NULL){
			Py_DECREF(self);
			return NULL;
		}

		self->value = (PyBytesObject*)PyBytes_FromString("");
		if (self->value == NULL){
			Py_DECREF(self);
			return NULL;
		}
		self->qtype = 0;
		self->qcls = 0;
		self->ttl = 0;
	}
	return (PyObject*)self;
}

static PyMemberDef RR_members[] = {
	{ "domain_name", T_OBJECT_EX, offsetof(RR, domain_name), 0, "domain name parsed from dns response" },
	{ "value", T_OBJECT_EX, offsetof(RR, value), 0, "value parsed from dns response, may ip or cname" },
	{ "qtype", T_USHORT, offsetof(RR, qtype), READONLY, "query type of resource record. `READONLY`" },
	{ "qcls", T_USHORT, offsetof(RR, qcls), READONLY, "query class of resource record. `READONLY`" },
	{ "ttl", T_UINT, offsetof(RR, ttl), READONLY, "ttl of resource record. `READONLY`" },
	{NULL}
};

PyDoc_STRVAR(RR_doc,
	"RR(domain_name: bytes, value: bytes, qtype: int, qcls: int, ttl: int) -> RR object\n\
	resource record of DNS, see https://www.ietf.org/rfc/rfc1035.txt for detail");

PyTypeObject RRType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"resolvers.RR",						//tp_name,
	sizeof(RR),						//tp_basicsize
	0,								//tp_itemsize
	(destructor)RR_dealloc,			//tp_dealloc
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
	RR_doc,		//tp_doc
	0,								//tp_traverse
	0,								//tp_clear
	0,								//tp_richcompare
	0,								//tp_weaklistoffset
	0,								//tp_iter
	0,								//tp_iternext
	0,								//tp_methods
	RR_members,						//tp_members
	0,								//tp_getset
	0,								//tp_base
	0,								//tp_dict
	0,								//tp_descr_get
	0,								//tp_descr_set
	0,								//tp_dictoffset
	(initproc)RR_init,				//tp_init
	0,								//tp_alloc
	RR_new							//tp_new
};

// DNSParser define

typedef struct{
	unsigned int start;
	unsigned int len;
} Inteval;

static void 
DNSParser_dealloc(DNSParser* self){
	Py_XDECREF(self->data);
	Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject* _class_attrs(){
	PyObject* d = PyDict_New();
	PyDict_SetItem(d, PyUnicode_FromString("QTYPE_A"), PyLong_FromLong(QTYPE_A));
	PyDict_SetItem(d, PyUnicode_FromString("QTYPE_NS"), PyLong_FromLong(QTYPE_NS));
	PyDict_SetItem(d, PyUnicode_FromString("QTYPE_CNAME"), PyLong_FromLong(QTYPE_CNAME));
	PyDict_SetItem(d, PyUnicode_FromString("QTYPE_AAAA"), PyLong_FromLong(QTYPE_AAAA));
	PyDict_SetItem(d, PyUnicode_FromString("QTYPE_ANY"), PyLong_FromLong(QTYPE_ANY));
	PyDict_SetItem(d, PyUnicode_FromString("QCLASS_IN"), PyLong_FromLong(QCLASS_IN));
	return d;
}

static PyObject*
DNSParser_new(PyTypeObject *type, PyObject *args, PyObject *kwds){
	DNSParser* self = (DNSParser*)type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;
	self->data = (PyBytesObject*)PyBytes_FromString("");
	if (self->data == NULL){
		Py_DECREF(self);
		return NULL;
	}
	self->offset = 0;
	return (PyObject*)self;
}

static int
DNSParser_init(DNSParser* self, PyObject *args, PyObject *kwds){
	PyObject* d = NULL, *tmp;
	if (!PyArg_ParseTuple(args, "S", &d)){
		return -1;
	}
	if (d){
		tmp = (PyObject*)self->data;	//不能先减refcount
		Py_INCREF(d);
		self->data = (PyBytesObject*)d;
		Py_XDECREF(tmp);
	}
	self->offset = 0;
	return 0;
}

static PyObject*
DNSParser_forward(DNSParser* self, PyObject* op){
	if (!PyLong_Check(op)){
		PyErr_SetString(PyExc_TypeError, "an integer is required");
		return NULL;
	}
	PyLongObject* i = (PyLongObject*)op;
	self->offset += *(i->ob_digit);
	Py_RETURN_NONE;
}

//从resp中解析出长度值(short), 并移动offset
static unsigned short short_from_resp(DNSParser* self) {
	register unsigned short res = unpacks(self->data->ob_sval + self->offset);
	self->offset += 2;
	return res;
}

//从resp中解析出长度值(int), 并移动offset
static unsigned int int_from_resp(DNSParser* self) {
	register unsigned short res = unpacki(self->data->ob_sval + self->offset);
	self->offset += 4;
	return res;
}

static PyObject*
DNSParser_parse_domain(DNSParser* self){
	register char* data = self->data->ob_sval;
	register unsigned int up = 0, i = self->offset, part_count = 0;
	register unsigned int j = 0, copied = 0, domain_length = 0;	//域名长度
	Inteval parts[20] = {0};

	while (GET_BYTE(self->data, i) != DOMAIN_END){
		unsigned char length = GET_BYTE(self->data, i);
		if (length >= 0xc0){
			if (i >= self->offset)
				self->offset += 2;
			i = unpacks(data + i) - 0xc000;
			continue;
		}
		up = i + length + 1;

		Inteval part = {i+1, length};
		*(parts + part_count) = part; part_count++;	//	添加到队列

		domain_length += (length + 1);	//. 要占一位

		if (up >= self->offset)
			self->offset += (length + 1);
		i = up;
	}
	domain_length--;	//上面多加了一个.

	if (up >= self->offset)
		self->offset += 1;

	if (domain_length <= 1){
		PyErr_SetString(PyExc_RuntimeError, "bad DNS response");
		return NULL;
	}

	PyBytesObject *op = (PyBytesObject *)PyBytes_FromSize(domain_length, 0);
	if (op == NULL)
		return NULL;
	char* domain = op->ob_sval;

	for (; j < part_count; j++){
		Inteval part = *(parts + j);
		memcpy(domain + copied, data + part.start, part.len);
		copied += part.len;
		if (j != part_count - 1){
			*(domain + copied) = '.';
			copied += 1;
		}
	}
	return (PyObject*)op;
}

static char dns_req_header[] = {1, 0, 0, 1, 0, 0, 0, 0, 0, 0 };

#define MAX_HOST_LEN 255

static PyObject*
DNSParser_build_request(DNSParser* self, PyObject *args){
	register PyObject* dn = NULL;
	register PyBytesObject* b = NULL;
	register char c = DNS_REQ_HEADER_LEN, e = 0;
	register char part_len = 0;
	
	unsigned short qtype = 0, id = 0, qcls = 0;

	if (!PyArg_ParseTuple(args, "SHH", &dn, &qtype, &id)){
		return NULL;
	}

	b = (PyBytesObject*)dn;
	if(b->ob_base.ob_size > MAX_HOST_LEN){
		PyErr_SetString(PyExc_ValueError, "hostname too long");
		return NULL;
	}

	qtype = htons(qtype);
	qcls = htons(QCLASS_IN);

	register char s = 0;
	register size_t size = DNS_REQ_SIZE(b->ob_base.ob_size);

	PyBytesObject* req = (PyBytesObject*)PyBytes_FromSize(size, 0);
	if (req == NULL)
		return NULL;
	id = ntohs(id);
	memcpy(req->ob_sval, &id, 2);
	memcpy(req->ob_sval + 2, dns_req_header, DNS_REQ_HEADER_LEN - 2);
	while (e <= b->ob_base.ob_size){
		if (*(b->ob_sval + e) == '.' || e == b->ob_base.ob_size){
			part_len = e - s;
			if (part_len > MAX_DNS_PART_LEN || part_len <= 0){
				PyErr_SetString(PyExc_RuntimeError, "invalid hostname");
				return NULL;
			}
			*(req->ob_sval + c) = part_len;
			c++;
			memcpy(req->ob_sval + c, b->ob_sval + s, e - s);
			c += part_len;
			s = e + 1;
		}
		e++;
	}
	//copy tail \x00\x00\x01\x00\x01
	*(req->ob_sval + c) = 0;	//\x00
	memcpy(req->ob_sval + c + 1, &qtype, 2);
	memcpy(req->ob_sval + c + 3, &qcls, 2);
	req->ob_sval[size] = '\0';
	return (PyObject*)req;
}

//rrs type is list
static PyObject*
DNSParser_parse_rrs(DNSParser* self, PyObject* rrs, size_t n){
	if (n == 0)
		return rrs;
	register char* d = self->data->ob_sval;
	register unsigned short qtype = 0, qcls = 0, data_length = 0;
	register unsigned int ttl = 0;
	for (size_t i = 0; i < n; i++){
		
		PyObject* domain = DNSParser_parse_domain(self);

		qtype = short_from_resp(self);
		qcls = short_from_resp(self);
		ttl = int_from_resp(self);
		data_length = short_from_resp(self);
		register PyObject* ip = NULL;

		if (qtype != QTYPE_A && qtype != QTYPE_AAAA){
			ip = DNSParser_parse_domain(self);
		}
		else{
			int af = 0;
			if (qtype == QTYPE_A){
				af = AF_INET;
			}
			else{
				af = AF_INET6;
			}
			ip = socket_inet_ntop(af, d + self->offset, data_length);
			self->offset += data_length;
		}
		if (ip == NULL)
			return NULL;

		RR* rr = (RR*)RR_new(&RRType, NULL, NULL);
		if (rr == NULL)
			return NULL;
		rr->domain_name = (PyBytesObject*)domain;
		rr->qcls = qcls;
		rr->qtype = qtype;
		rr->ttl = ttl;
		rr->value = (PyBytesObject*)ip;

		PyList_Append(rrs, (PyObject*)rr);
	}
	return (PyObject*)rrs;
}

static PyObject*
DNSParser_parse_response(DNSParser* self){
	if (self->offset != 0){
		PyErr_SetString(PyExc_RuntimeError, "offset is not 0");
		return NULL;
	}
	self->offset += 6;		//去头

	unsigned short answer_rrs = short_from_resp(self);
	unsigned short authority_rrs = short_from_resp(self);
	unsigned short addtional_rrs = short_from_resp(self);

	PyObject* query_domain = DNSParser_parse_domain(self);
	unsigned short qtype = ntohs(*((unsigned short*)(self->data->ob_sval + self->offset)) );
	PyObject* query_type = PyLong_FromLong(qtype);
	self->offset += 4;		//忽略query_type 和  query_cls, 共4字节

	PyObject* rrs = PyList_New(0);
	if (rrs == NULL)
		return NULL;
	if (DNSParser_parse_rrs(self, rrs, answer_rrs) == NULL)
		return NULL;
	if (DNSParser_parse_rrs(self, rrs, authority_rrs) == NULL)
		return NULL;
	if (DNSParser_parse_rrs(self, rrs, addtional_rrs) == NULL)
		return NULL;
	//Py_INCREF(rrs);
	PyObject* res = PyTuple_New(3);
	PyTuple_SET_ITEM(res, 0, query_domain);
	PyTuple_SET_ITEM(res, 1, query_type);
	PyTuple_SET_ITEM(res, 2, rrs);
	Py_INCREF(res);
	return res;
	//Py_RETURN_NONE;
}

static PyMemberDef DNSParser_members[] = {
	{ "data", T_OBJECT_EX, offsetof(DNSParser, data), 0, "bytes received from network" },
	{ "offset", T_UINT, offsetof(DNSParser, offset), 0, "cursor used when parse domain" },
	{NULL}
};

PyDoc_STRVAR(forward_doc, 
	"forward(nbytes: int)\n\
	\n\
	skip n bytes by add `nbytes` to `offset` field");

PyDoc_STRVAR(parse_domain_doc, 
	"parse_domain() -> bytes\n\
	\n\
	low-level api.\n\
	parse domain name from `data`. it will modify `offset` field");

PyDoc_STRVAR(build_request_doc,
	"build_request(hostname: bytes, qtype: int, tid: int) -> bytes\n\
	\n\
	build DNS request package with hostname and qtype with transaction id.\n\
	\n\
	type of `hostname` must be bytes; transaction id must be a short int, \n\
	which can be generated by `os.urandom(2)`; and qtype must be one of \n\
		`DNSParser.QTYPE_A`\n\
		`DNSParser.QTYPE_AAAA`\n\
		`DNSParser.QTYPE_CNAME`\n\
		`DNSParser.QTYPE_NS`\n\
		`DNSParser.QTYPE_ANY`\n\
	return DNS request package");

PyDoc_STRVAR(parse_resp_doc,
	"parse_response() -> Tuple(hostname: bytes, qtype: int rrs: list)\n\
	high-level api.\n\
	parse DNS resource record from data\n\
	hostname is the same as the one which passed to `build_request` method,\n\
	and its type is bytes.\n\
	\n\
	each item in rrs is an instance of class `RR`");

PyDoc_STRVAR(DNSParser_doc,
	"DNSParser(dns_response: bytes) -> DNSParser object\n\
	\n\
	build a DNS parser with DNS response");

static PyMethodDef DNSParser_methods[] = {
	{ "forward", (PyCFunction)DNSParser_forward, METH_O, forward_doc},
	{ "parse_domain", (PyCFunction)DNSParser_parse_domain, METH_NOARGS, parse_domain_doc },
	{ "build_request", (PyCFunction)DNSParser_build_request, METH_VARARGS | METH_CLASS, build_request_doc },
	{ "parse_response", (PyCFunction)DNSParser_parse_response, METH_NOARGS, parse_resp_doc },
	{NULL}
};

PyTypeObject DNSParserType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"resolvers.DNSParser",			//tp_name,
	sizeof(DNSParser),			//tp_basicsize
	0,								//tp_itemsize
	(destructor)DNSParser_dealloc,//tp_dealloc
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
	DNSParser_doc,					//tp_doc
	0,								//tp_traverse
	0,								//tp_clear
	0,								//tp_richcompare
	0,								//tp_weaklistoffset
	0,								//tp_iter
	0,								//tp_iternext
	DNSParser_methods,				//tp_methods
	DNSParser_members,				//tp_members
	0,								//tp_getset
	0,								//tp_base
	_class_attrs(),					//tp_dict
	0,								//tp_descr_get
	0,								//tp_descr_set
	0,								//tp_dictoffset
	(initproc)DNSParser_init,		//tp_init
	0,								//tp_alloc
	DNSParser_new					//tp_new
};

static struct PyModuleDef parser = {
	PyModuleDef_HEAD_INIT,
	"dnsparser",
	"Copyright 2019-2019 wcsjtu\n\nspeed up for dns parser\n\nversion:1.0",
	-1,
	NULL
};

PyMODINIT_FUNC
PyInit_dnsparser(void){
    PyObject* m = PyModule_Create(&parser);
    if (!m){
		return NULL;
	}
    if (PyType_Ready(&RRType) < 0 ||
		PyType_Ready(&DNSParserType) < 0){
		return NULL;
	}
    Py_INCREF(&RRType);
    Py_INCREF(&DNSParserType);

    PyModule_AddObject(m, "RR", (PyObject*)&RRType);
	PyModule_AddObject(m, "DNSParser", (PyObject*)&DNSParserType);
    
    return m;
}