This is some very old code that I used to use for managing log output
for Apache's httpd. In the Apache config you can specify a program or
log daemon to write error logs to as documented here:

http://httpd.apache.org/docs/2.2/logs.html#piped
http://httpd.apache.org/docs/2.2/mod/mod_log_config.html#formats

So this tool allows one to split up logs according to a custom file
path. The specific log file that an entry is written to is calculated
using fields from the entry as well as any strftime format specifiers
that you specify as an argument. This can be used for setting up logs
in a format that can be used to generate some useful stats about your
site.

The tool itself explicitly trusts what you tell it, so it is probably
necessary to mention that if you base your path off of user-supplied
data and not a field that comes from Apache and your configuration then
an attacker can possibly write their log to an arbitrary file by injecting
relative path components. Therefore it is suggested that you do not 
trust any user-supplied field specified in the LogFormat argument and
explicitly specify the ServerName or UseCanonicalName parameters for
each of your vhosts.

Usage:
    plogg.py [-c columns] [-f maxfiles] path-template

columns -- the number of columns in an apache error entry
maxfiles -- is the maximum number of files to keep handles open to.
            one per directory or should be good enough.

path-template -- This specifies the path that the log entry should be
                 written to. A path can optionally (and should) contain
                 format specifiers with which the log file will be
                 created. This can be used, as an example, to split up
                 logfiles according to the vhost, the month, or year,
                 or a combination of all of the above.

                 The path-template field can contain any of the format
                 specifiers from strftime(3), or a field number which
                 will correspond to the field from the Apache log entry.

Example in your Apache config:
    LogFormat "%v %A %a %p %s %u %H %I %O %m \"%f\" \"%q\" %r"
    CustomLog "| plogg.py -c 13 $LOGPATH/%1/%Y-%m/%d.log"

This will write each log entry to a file named according to the numerical day in
the directory with the vhost and year+month.

-arizvisa@gmail.com
