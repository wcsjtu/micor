#include "cares.h"
#include "socketutil.h"

extern PyTypeObject RRType;

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
	DNS_REQ_TAIL_LEN + domain_len + 1)	//n个点对应着n+1段的长度, 再加上\x00结束符

#define PyBytesObject_SIZE (offsetof(PyBytesObject, ob_sval) + 1)
#define GET_BYTE(b, i) ( (unsigned char)(*(b->ob_sval + i)) )	//从PyBytesObject中取出byte


static PyBytesObject *nullstring;
static char dns_req_header[] = { 'c', 'e', 1, 0, 0, 1, 0, 0, 0, 0, 0, 0 };

typedef struct{
	unsigned int start;
	unsigned int len;
} Inteval;


size_t unpack(char* sd, size_t n){
	unsigned char* d = (unsigned char*)sd;
	if (n == 1){
		return *d;
	}
	size_t r = 0;
	for (size_t i = 0; i < n; i++){
		r |= (*(d + i) << ((n - i - 1) * 8));
	}
	return r;
}

PyObject *
PyBytes_FromSize(Py_ssize_t size, int use_calloc)
{
	PyBytesObject *op;
	assert(size >= 0);

	if (size == 0 && (op = nullstring) != NULL) {
#ifdef COUNT_ALLOCS
		null_strings++;
#endif
		Py_INCREF(op);
		return (PyObject *)op;
	}

	if ((size_t)size > (size_t)PY_SSIZE_T_MAX - PyBytesObject_SIZE) {
		PyErr_SetString(PyExc_OverflowError,
			"byte string is too large");
		return NULL;
	}

	/* Inline PyObject_NewVar */
	if (use_calloc)
		op = (PyBytesObject *)PyObject_Calloc(1, PyBytesObject_SIZE + size);
	else
		op = (PyBytesObject *)PyObject_Malloc(PyBytesObject_SIZE + size);
	if (op == NULL)
		return PyErr_NoMemory();
	(void)PyObject_INIT_VAR(op, &PyBytes_Type, size);
	op->ob_shash = -1;
	if (!use_calloc)
		op->ob_sval[size] = '\0';
	/* empty byte string singleton */
	if (size == 0) {
		nullstring = op;
		Py_INCREF(op);
	}
	return (PyObject *)op;
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


static void 
DNSParser_dealloc(DNSParser* self){
	Py_XDECREF(self->data);
	Py_TYPE(self)->tp_free((PyObject*)self);
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

//从resp中解析出长度值, 并移动offset
size_t get_count_from_resp(DNSParser* self, size_t n){
	register size_t res = unpack(self->data->ob_sval + self->offset, n);
	self->offset += n;
	return res;
}

static PyObject*
DNSParser_parse_domain(DNSParser* self){
	register char* data = self->data->ob_sval;
	register unsigned int up = 0, i = self->offset, part_count = 0;
	register unsigned int j = 0, copied = 0, domain_length = 0;	//域名长度
	Inteval parts[20] = {};

	while (GET_BYTE(self->data, i) != DOMAIN_END){
		unsigned char length = GET_BYTE(self->data, i);
		if (length >= 0xc0){
			if (i >= self->offset)
				self->offset += 2;
			i = unpack(data + i, 2) - 0xc000;
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

static PyObject*
DNSParser_build_request(DNSParser* self, PyObject *args){
	register PyObject* dn = NULL;
	register PyBytesObject* b = NULL;
	register size_t c = DNS_REQ_HEADER_LEN, e = 0, part_len = 0;
	
	register unsigned short qtype = 0;

	if (!PyArg_ParseTuple(args, "SH", &dn, &qtype)){
		return NULL;
	}

	b = (PyBytesObject*)dn;
	register char tail[] = {0, 0, qtype, 0, QCLASS_IN};

	register size_t s = 0, dnl = b->ob_base.ob_size;
	register size_t size = DNS_REQ_SIZE(dnl);

	PyBytesObject* req = (PyBytesObject*)PyBytes_FromSize(size, 0);
	if (req == NULL)
		return NULL;

	memcpy(req->ob_sval, dns_req_header, DNS_REQ_HEADER_LEN);
	while (e <= dnl){
		if (*(b->ob_sval + e) == '.' || e == dnl){
			part_len = e - s;
			if (part_len > MAX_DNS_PART_LEN || part_len <= 0){
				PyErr_SetString(PyExc_RuntimeError, "invalid DNS response");
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
	memcpy(req->ob_sval + c, tail, DNS_REQ_TAIL_LEN);
	req->ob_sval[size] = '\0';
	return (PyObject*)req;
}

//rrs type is list
static PyObject*
DNSParser_parse_rrs(DNSParser* self, PyObject* rrs, size_t n){
	if (n == 0)
		return rrs;
	register char* d = self->data->ob_sval;
	register size_t qtype = 0, qcls = 0, ttl = 0, data_length = 0;
	for (size_t i = 0; i < n; i++){
		
		PyObject* domain = DNSParser_parse_domain(self);

		qtype = get_count_from_resp(self, 2);
		qcls = get_count_from_resp(self, 2);
		ttl = get_count_from_resp(self, 4);
		data_length = get_count_from_resp(self, 2);
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

	size_t answer_rrs = get_count_from_resp(self, 2);
	size_t authority_rrs = get_count_from_resp(self, 2);
	size_t addtional_rrs = get_count_from_resp(self, 2);

	PyObject* query_domain = DNSParser_parse_domain(self);
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
	PyObject* res = PyTuple_New(2);
	PyTuple_SET_ITEM(res, 0, query_domain);
	PyTuple_SET_ITEM(res, 1, rrs);
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
	"build_request(hostname: bytes, qtype: int) -> bytes\n\
	\n\
	build DNS request package with hostname and qtype. type of `hostname`\n\
	must be bytes; and qtype must be one of \n\
		`DNSParser.QTYPE_A`\n\
		`DNSParser.QTYPE_AAAA`\n\
		`DNSParser.QTYPE_CNAME`\n\
		`DNSParser.QTYPE_NS`\n\
		`DNSParser.QTYPE_ANY`\n\
	return DNS request package");

PyDoc_STRVAR(parse_resp_doc,
	"parse_response() -> Tuple(hostname: bytes, rrs: list)\n\
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


static PyTypeObject DNSParserType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"cares.DNSParser",			//tp_name,
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

PyTypeObject* DNSParserTypePtr = &DNSParserType;