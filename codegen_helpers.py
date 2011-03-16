# -*- coding: utf-8 -*-

def genSingleEncode(spec, cValue, unresolved_domain):
    buffer = []
    type = spec.resolveDomain(unresolved_domain)
    if type == 'shortstr':
        buffer.append("pieces << %s.bytesize.chr" % (cValue,))
        buffer.append("pieces << %s" % (cValue,))
    elif type == 'longstr':
        buffer.append("pieces << [%s.bytesize].pack(PACK_CACHE[:N])" % (cValue,))
        buffer.append("pieces << %s" % (cValue,))
    elif type == 'octet':
        buffer.append("pieces << [%s].pack(PACK_CACHE[:c])" % (cValue,))
    elif type == 'short':
        buffer.append("pieces << [%s].pack(PACK_CACHE[:n])" % (cValue,))
    elif type == 'long':
        buffer.append("pieces << [%s].pack(PACK_CACHE[:N])" % (cValue,))
    elif type == 'longlong':
        buffer.append("pieces << AMQ::Hacks.pack_64_big_endian(%s)" % (cValue,))
    elif type == 'timestamp':
        buffer.append("pieces << AMQ::Hacks.pack_64_big_endian(%s)" % (cValue,))
    elif type == 'bit':
        raise "Can't encode bit in genSingleEncode"
    elif type == 'table':
        buffer.append("pieces << AMQ::Protocol::Table.encode(%s)" % (cValue,))
    else:
        raise "Illegal domain in genSingleEncode", type

    return buffer

def genSingleDecode(spec, field):
    cLvalue = field.ruby_name
    unresolved_domain = field.domain

    if cLvalue == "known_hosts":
        import sys
        print >> sys.stderr, field, field.ignored

    type = spec.resolveDomain(unresolved_domain)
    buffer = []
    if type == 'shortstr':
        buffer.append("length = data[offset, 2].unpack(PACK_CACHE[:c])[0]")
        buffer.append("offset += 1")
        buffer.append("%s = data[offset, length]" % (cLvalue,))
        buffer.append("offset += length")
    elif type == 'longstr':
        buffer.append("length = data[offset, 5].unpack(PACK_CACHE[:N]).first")
        buffer.append("offset += 4")
        buffer.append("%s = data[offset, length]" % (cLvalue,))
        buffer.append("offset += length")
    elif type == 'octet':
        buffer.append("%s = data[offset, 1].unpack(PACK_CACHE[:c]).first" % (cLvalue,))
        buffer.append("offset += 1")
    elif type == 'short':
        buffer.append("%s = data[offset, 3].unpack(PACK_CACHE[:n]).first" % (cLvalue,))
        buffer.append("offset += 2")
    elif type == 'long':
        buffer.append("%s = data[offset, 5].unpack(PACK_CACHE[:N]).first" % (cLvalue,))
        buffer.append("offset += 4")
    elif type == 'longlong':
        buffer.append("%s = AMQ::Hacks.unpack_64_big_endian(data[offset, 8]).first" % (cLvalue,))
        buffer.append("offset += 8")
    elif type == 'timestamp':
        buffer.append("%s = data[offset, 7].unpack(PACK_CACHE[:N2]).first" % (cLvalue,))
        buffer.append("offset += 8")
    elif type == 'bit':
        raise "Can't decode bit in genSingleDecode"
    elif type == 'table':
        buffer.append("table_length = Table.length(data[offset, 5])")
        buffer.append("%s = Table.decode(data[offset, table_length - offset + 1])" % (cLvalue,))
    else:
        raise StandardError("Illegal domain '" + type + "' in genSingleDecode")

    return buffer



def genSingleSimpleDecode(spec, field):
    cLvalue = field.ruby_name
    unresolved_domain = field.domain

    if cLvalue == "known_hosts":
        import sys
        print >> sys.stderr, field, field.ignored

    type = spec.resolveDomain(unresolved_domain)
    buffer = []
    if type == 'shortstr':
        # buffer.append("length = data.unpack(PACK_CACHE[:c])[0]")
        # buffer.append("result = data[offset..-1]")
        # buffer.append("raise 'Bad size: #{length} expected, got #{result.bytesize}' if result.bytesize != length")
        # buffer.append("result")
        buffer.append("data")
    elif type == 'longstr':
        # buffer.append("length = data.unpack(PACK_CACHE[:N])[0]")
        # buffer.append("result = data[offset..-1]")
        # buffer.append("raise 'Bad size: #{length} expected, got #{result.bytesize}' if result.bytesize != length")
        # buffer.append("result")
        buffer.append("data")
    elif type == 'octet':
        buffer.append("data.unpack(PACK_CACHE[:c]).first")
    elif type == 'short':
        buffer.append("data.unpack(PACK_CACHE[:n]).first")
    elif type == 'long':
        buffer.append("data.unpack(PACK_CACHE[:N]).first")
    elif type == 'longlong':
        buffer.append("AMQ::Hacks.unpack_64_big_endian(data).first")
    elif type == 'timestamp':
        buffer.append("Time.at(data.unpack(PACK_CACHE[:N2]).last)")
    elif type == 'bit':
        raise "Can't decode bit in genSingleDecode"
    elif type == 'table':
        buffer.append("Table.decode(data)")
    else:
        raise StandardError("Illegal domain '" + type + "' in genSingleSimpleDecode")

    return buffer


def genEncodeMethodDefinition(spec, m):
    def finishBits():
        if bit_index is not None:
            buffer.append("pieces << [bit_buffer].pack(PACK_CACHE[:c])")

    bit_index = None
    buffer = []

    for f in m.arguments:
        if spec.resolveDomain(f.domain) == 'bit':
            if bit_index is None:
                bit_index = 0
                buffer.append("bit_buffer = 0")
            if bit_index >= 8:
                finishBits()
                buffer.append("bit_buffer = 0")
                bit_index = 0
            buffer.append("bit_buffer = bit_buffer | (1 << %d) if %s" % (bit_index, f.ruby_name))
            bit_index = bit_index + 1
        else:
            finishBits()
            bit_index = None
            buffer += genSingleEncode(spec, f.ruby_name, f.domain)

    finishBits()
    return buffer

def genDecodeMethodDefinition(spec, m):
    buffer = []
    bitindex = None
    for f in m.arguments:
        if spec.resolveDomain(f.domain) == 'bit':
            if bitindex is None:
                bitindex = 0
            if bitindex >= 8:
                bitindex = 0
            if bitindex == 0:
                buffer.append("bit_buffer = data[offset, 2].unpack(PACK_CACHE[:c]).first")
                buffer.append("offset += 1")
                buffer.append("%s = (bit_buffer & (1 << %d)) != 0" % (f.ruby_name, bitindex))
                #### TODO: ADD bitindex TO THE buffer
            bitindex = bitindex + 1
        else:
            bitindex = None
            buffer += genSingleDecode(spec, f)
    return buffer
