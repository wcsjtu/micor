#include "dnsparser.h"

#define UNPACK(buf, n, tp) {\
	unsigned char* d = (unsigned char*)buf;\
	if(n == 1){\
		return *d;\
	}\
	tp r = 0; \
	for(tp i = 0; i< n; i++){\
		r |= (*(d + i) << ((n - i - 1) * 8));\
	}\
	return r;\
}

unsigned short unpacks(char* buf){
	UNPACK(buf, 2, unsigned short);
}

unsigned int unpacki(char* buf){
	UNPACK(buf, 4, unsigned int);
}

static PyBytesObject *nullstring;


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


#ifdef WIN32
PyObject *
socket_inet_ntop(int af, char* buf, int buf_len)
{
	struct sockaddr_in6 addr;
	DWORD addrlen, ret, retlen;
	char ip[Py_MAX(INET_ADDRSTRLEN, INET6_ADDRSTRLEN) + 1];

	if (af == AF_INET) {
		struct sockaddr_in * addr4 = (struct sockaddr_in *)&addr;

		if (buf_len != sizeof(struct in_addr)) {
			PyErr_SetString(PyExc_ValueError,
				"invalid length of packed IP address string");
			return NULL;
		}
		memset(addr4, 0, sizeof(struct sockaddr_in));
		addr4->sin_family = AF_INET;
		memcpy(&(addr4->sin_addr), buf, sizeof(addr4->sin_addr));
		addrlen = sizeof(struct sockaddr_in);
	}
	else if (af == AF_INET6) {
		if (buf_len != sizeof(struct in6_addr)) {
			PyErr_SetString(PyExc_ValueError,
				"invalid length of packed IP address string");
			return NULL;
		}

		memset(&addr, 0, sizeof(addr));
		addr.sin6_family = AF_INET6;
		memcpy(&(addr.sin6_addr), buf, sizeof(addr.sin6_addr));
		addrlen = sizeof(addr);
	}
	else {
		PyErr_Format(PyExc_ValueError,
			"unknown address family %d", af);
		return NULL;
	}

	retlen = sizeof(ip);
	ret = WSAAddressToStringA((struct sockaddr*)&addr, addrlen, NULL,
		ip, &retlen);

	if (ret) {
		PyErr_SetExcFromWindowsErr(PyExc_OSError, WSAGetLastError());
		return NULL;
	}
	else {
		return PyBytes_FromString(ip);
	}
}

#else
PyObject*
socket_inet_ntop(int af, char* buf, int buf_len){
	char ip[Py_MAX(INET_ADDRSTRLEN, INET6_ADDRSTRLEN) + 1];
	if (af == AF_INET){
		inet_ntop(AF_INET, buf, ip, INET_ADDRSTRLEN);
	} 
	else if( af == AF_INET6){
		inet_ntop(AF_INET6, buf, ip, INET6_ADDRSTRLEN);
	}
	else {
		PyErr_Format(PyExc_ValueError,
			"unknown address family %d", af);
		return NULL;
	}
	PyObject* res = PyBytes_FromString(ip);
	return res;
}
#endif