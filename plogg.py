#!/usr/bin/env python
import sys, re, time
import getopt

DEBUG = {
    'main' : 0,
    'cache' : 0,
    'lexlog' : 0,
    'parselog' : 0,
    'lextemplate' : 0,
    'parsetemplate' : 0,
    'fsresolver': 0
}

def log(message):
    '''fallback to stderr if we have issues'''
    sys.stderr.write(message + "\n")

def debug(type, message):
    if DEBUG[type]:
        s = '[debug-%s] %s'%(type, message)
        sys.stderr.write(s + "\n")
 
def usage():
    print "Usage: %s [-c columns] [-f maxfiles] path"%(sys.argv[0])

def warning(message):
    s = '[warn] %s'%message
    sys.stderr.write(s + "\n")

def fatal(message):
    s = '[fatal] %s'%message
    sys.stderr.write(s + "\n")
    sys.exit(1)

### base objects
class TOKEN(object):
    value = None
    def __init__(self, value=''):
        self.value = str(value)

    def __nonzero__(self):
        return len(self.value) > 0

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return '(%s, "%s")'%(self.__class__, str(self.value))

    def __add__(self, t):
        return TOKEN(self.value + t.value)

class parser(object):
    def collect(self, data, pos, *next):
        if data[pos] in next:
            return pos
        return self.collect(data, pos+1, *next)

    def lex(self, data):
        raise NotImplementedError

    def parse(self, data):
        raise NotImplementedError

### parsing apache logs
class log_SEPARATOR(TOKEN):
    pass

class apachelog(parser):
    SEPARATOR = ' '
    def lex(self, data):
        debug('lexlog', 'lexing: %s'%data)

        index = 0
        try:
            while index < len(data):
                cur = data[index]

                if cur == '\\':
                    typ, next = TOKEN, index + 2

                elif cur == self.SEPARATOR:
                    typ, next = log_SEPARATOR, index + 1

                elif cur == '(':
                    typ, next = TOKEN, self.collect(data, index+1, ')')+1

                elif cur == '[':
                    typ, next = TOKEN, self.collect(data, index+1, ']')+1

                elif cur == '"':
                    typ, next = TOKEN, self.collect(data, index+1, '"')+1

                else:
                    typ, next = TOKEN, self.collect(data, index, self.SEPARATOR)

                debug('lexlog', '%s found at data[%d:%d]'%(repr(typ), index, next))
                yield typ( data[index:next] )
                index = next

        except IndexError:
            debug('lexlog', 'garbage found at data[%d:]: %s'%(index, data[index:]))
            yield TOKEN( data[index:] )

    def parse(self, data, max=0):
        debug('parselog', 'parsing: %s'%data)
        count = 0
        lexer = self.lex(data)
        while (max == 0) or (count < max):
            n = lexer.next()
            if type(n) == log_SEPARATOR:
                continue

            debug('parselog', 'yielding %s'%type(n))
            yield n

            count += 1

        debug('parselog', 'parsed %d fields'%count)
        if count >= max:
            res = TOKEN()
            try:
                while True:
                    n = lexer.next()
                    res += n
            except StopIteration:
                pass

            debug('parselog', 'garbage (user-specified): %s'%res)
            yield res

### parsing a format specifier
class fmt_FORMAT(TOKEN):
    format = None
    def __init__(self, value):
        TOKEN.__init__(self, value)
        self.format = value[1]

class fmt_BACKSLASH(TOKEN):
    def __str__(self):
        return self.value[1:]

class template(parser):
    def lex(self, data):
        debug('lextemplate', 'lexing: %s'%data)

        index = 0
        try:
            while index < len(data):
                if data[index] == '\\':
                    typ, next = fmt_BACKSLASH, index + 2
                elif data[index] == '%':
                    typ, next = fmt_FORMAT, index + 2   #XXX: we limit format specifiers to 1 character here
                else:
                    typ, next = TOKEN, index + 1    #XXX: yes, i know this is not efficient

                debug('lextemplate', '%s found at data[%d:%d]'%(repr(typ), index, next))
                yield typ( data[index:next] )
                index = next

        except IndexError:
            debug('lextemplate', 'garbage found at data[%d:]: %s'%(index, data[index:]))
            yield TOKEN( data[index:] )

    def parse(self, data, *args):
        debug('parsetemplate', 'parsing: %s'%data)

        tok = TOKEN()
        for n in self.lex(data):
            if type(n) == TOKEN:
                tok += n
                continue

            if tok:
                debug('parsetemplate', 'yielding (collected): %s'%repr(tok))
                yield tok
                tok = TOKEN()

            debug('parsetemplate', 'yielding: %s'%repr(n))
            yield n

        # return what we gather'd only if necessary
        if tok:
            debug('parsetemplate', 'yielding (collected): %s'%repr(tok))
            yield tok

### resolving all the formats in a format specifier
class fs_resolver(object):

    def strftime(self, fmt):
        '''calculates format on the fly'''
        def __res(args):
            return time.strftime('%%%s'%fmt, time.gmtime())
        return __res

    def fieldnum(self, n):
        def __res(args):
            return args[n]
        return __res
    
    def __init__(self, tokens):
        object.__init__(self)
        self.tokens = tokens

        l = []
        # time.strftime specifiers - aAbBcdHIjmMpSUwWxXyYZ%
        for n in 'aAbBcdHIjmMpSUwWxXyYZ%':
            fn = self.strftime(n)
            l.append( (n, fn) )

        # field number - 1-9
        for n in range(1,9):
            fn = self.fieldnum(n-1)
            l.append( (str(n), fn) )

        # concatenate (yay)
        self.specifiers = dict(l)

    def resolve(self, args):
        s = ''
        for n in self.tokens:
            debug('fsresolver', 'Encountered %s: %s'%(type(n), str(n)))
            if type(n) == fmt_FORMAT:
                s += str(self.specifiers[n.format](args))
            else:
                s += str(n)
        return s

class odict(object):
    '''very cheaply implemented ordered dict'''
    _items = None

    def __init__(self, iterable=None):
        self._items = []
        if iterable:
            for k,v in iterable:
                self._items.append( (k,v) )

    def _keyidx(self, key):
        i = 0
        for i in range( len(self._items) ):
            k,v = self._items[i]
            if key == k:
                return i
        raise KeyError(key)

    def __len__(self):
        return len(self._items)

    def __contains__(self, k):
        return k in self.keys()

    # woo copy and paste
    def keys(self):
        return [ k for k,v in self._items ]
    def values(self):
        return [ v for k,v in self._items ]
    def items(self):
        return self._items[:]

    def __iter__(self):
        for k,v in self._items:
            yield k

    def iterkeys(self):
        for k in self.keys():
            yield k

    def itervalues(self):
        for v in self.values():
            yield v

    def __getitem__(self, k):
        i = self._keyidx(k)
        k,v = self._items[i]
        return v

    def __setitem__(self, k, v):
        try:
            self._items[ self._keyidx(k) ] = (k, v)

        except KeyError:
            self._items.append( (k,v) )

    def __delitem__(self, k):
        i = self._keyidx(k)
        del( self._items[i] )

    def __repr__(self):
        return repr(self._items)

class filecache(odict):
    maxlength = None
    destructor = None

    def __init__(self, length, destructor=None):
        odict.__init__(self)

        self.maxlength = length
        self.destructor = destructor

    def __getitem__(self, k):
        n = odict.__getitem__(self, k)

        debug('cache', 'cache %s> found %s'%(repr(self), k))

        # XXX: hack to move item to the end of the list
        odict.__delitem__(self, k)
        odict.__setitem__(self, k, n)

        return n

    def __setitem__(self, k, v):
        # remove the newest item
        if (self.maxlength) > 0 and (len(self) >= self.maxlength):
            name = odict.keys(self)[0]
            debug('cache', 'cache %s> expiring %s to make space for %s'%( repr(self), name, k ) )
            if self.destructor:
                n = odict.__getitem__(self, name)
                self.destructor(n)
            odict.__delitem__(self, name)

        # continue adding it
        debug('cache', 'cache %s> adding %s'%( repr(self), k ) )
        odict.__setitem__(self, k, v)

    def __repr__(self):
        return repr(type(self))
        

if __name__ == '__main__':
    max = 0
    filecount = 0

    debug('main', 'starting %s %s'%(sys.argv[0], repr(sys.argv)))

    ## ignorance checking
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'c:f:')
        path = args[0]

        # fetch some cmdline options
        opts = dict(opts)
        if '-c' in opts.keys():
            max = int(opts['-c'])

        if '-f' in opts.keys():
            filecount = int(opts['-f'])

    except:
        usage()
        sys.exit(0)

    ## precompile our template
    tokens = list( template().parse(path) )
    debug('main', 'compiled template to: %s'% repr(tokens))

    formatter = fs_resolver(tokens)

    ## some shit that we're gonna need
    cache = filecache(length=filecount, destructor=file.close)
    logparse = apachelog()

    ## main loop
    debug('main', 'entering read loop')

    while True:
        l = sys.stdin.readline()    # thank you: http://mail.python.org/pipermail/python-list/2007-April/435322.html
        if not l:
            break
        
        ## fetch and parse our fields into a pathname
        try:
            fields = list( logparse.parse(l, max) )
            debug('main', 'parsed fields: %s'%repr([str(n) for n in fields]))
            pathname = formatter.resolve(fields)

        except Exception, (x, msg):
            ## hmm...admin not a clue?
            warning('Unable to parse %s using %s: %s'%( ''.join([str(n) for n in self.tokens]), args, msg))
            continue

        ## search for the file in our cache
        try:
            try:
                out = cache[pathname]
            except KeyError:
                out = file(pathname, 'a', 0)
                cache[pathname] = out

            ## write to the log
            out.write(l)
        except IOError, (x, msg):
            ## Ouch, we're unable to write to a file...go figure.
            warning('Unable to write to %s: %s'%(pathname, msg))
            log(l)

    debug('main', 'leaving read loop')
