#include "socketutil.h"

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