# Created on May 3, 2013
# 
# @author: Ross Miller
# 
# Copyright 2013, 2015 UT Battelle, LLC
# 
# This work was supported by the Oak Ridge Leadership Computing Facility at
# the Oak Ridge National Laboratory, which is managed by UT Battelle, LLC for
# the U.S. DOE (under the contract No. DE-AC05-00OR22725).
# 
# This file is part of DDNTool_v2.
# 
# DDNTool_v2 is free software: you can redistribute it and/or modify it under
# the terms of the UT-Battelle Permissive Open Source License.  (See the
# License.pdf file for details.)
# 
# DDNTool_v2 is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.


import logging
import mysql.connector


# names for the various database tables
# Note: the names need to be unicode because that's what we get back from
# a SHOW TABLES statement
TABLE_NAMES = {
#             "MAIN_TABLE_NAME" : u"Main",
             "DISK_TABLE_NAME" : u"Disk",
             "LUN_TABLE_NAME" : u"LunInfo",
             "RAW_LUN_TABLE_NAME" : u"LunInfoRaw",
             "TIER_DELAY_TABLE_NAME" : u"TierDelays",
             "LUN_READ_REQUEST_SIZE_TABLE_NAME" : u"LunReadRequestSizes",
             "LUN_READ_REQUEST_LATENCY_TABLE_NAME" : u"LunReadRequestLatencies",
             "LUN_WRITE_REQUEST_SIZE_TABLE_NAME" : u"LunWriteRequestSizes",
             "LUN_WRITE_REQUEST_LATENCY_TABLE_NAME" : u"LunWriteRequestLatencies",
             "DD_READ_REQUEST_SIZE_TABLE_NAME" : u"DiskDriveReadRequestSizes",
             "DD_READ_REQUEST_LATENCY_TABLE_NAME" : u"DiskDriveReadRequestLatencies",
             "DD_WRITE_REQUEST_SIZE_TABLE_NAME" : u"DiskDriveWriteRequestSizes",
             "DD_WRITE_REQUEST_LATENCY_TABLE_NAME" : u"DiskDriveWriteRequestLatencies"
#define USER_TABLE_NAME             "Users"
 }
#

# Partially complete SQL statements for creating the request size
# and latency tables
PARTIAL_LUN_LATENCY_TABLE_DEF = \
    "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
    "LUN SMALLINT UNSIGNED NOT NULL, " \
    "16ms INT UNSIGNED NOT NULL, " \
    "32ms  INT UNSIGNED NOT NULL, " \
    "64ms INT UNSIGNED NOT NULL, " \
    "128ms INT UNSIGNED NOT NULL, " \
    "256ms INT UNSIGNED NOT NULL, " \
    "512ms INT UNSIGNED NOT NULL, " \
    "1s INT UNSIGNED NOT NULL, " \
    "2s INT UNSIGNED NOT NULL, " \
    "4s INT UNSIGNED NOT NULL, " \
    "8s INT UNSIGNED NOT NULL, " \
    "16s INT UNSIGNED NOT NULL, " \
    "Longer_Than_16s INT UNSIGNED NOT NULL, " \
    "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
    "INDEX( Hostname), INDEX( Disk_Num) )" \
    "ENGINE=HEAP" \
    ";"

PARTIAL_DD_LATENCY_TABLE_DEF = \
    "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
    "Disk_Num SMALLINT UNSIGNED NOT NULL, " \
    "4ms INT UNSIGNED NOT NULL, " \
    "8ms INT UNSIGNED NOT NULL, " \
    "16ms INT UNSIGNED NOT NULL, " \
    "32ms  INT UNSIGNED NOT NULL, " \
    "64ms INT UNSIGNED NOT NULL, " \
    "128ms INT UNSIGNED NOT NULL, " \
    "256ms INT UNSIGNED NOT NULL, " \
    "512ms INT UNSIGNED NOT NULL, " \
    "1s INT UNSIGNED NOT NULL, " \
    "2s INT UNSIGNED NOT NULL, " \
    "4s INT UNSIGNED NOT NULL, " \
    "Longer_Than_4s INT UNSIGNED NOT NULL, " \
    "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
    "INDEX( Hostname), INDEX( Disk_Num) )" \
    "ENGINE=HEAP" \
    ";"


PARTIAL_SIZE_TABLE_DEF = \
    "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
    "Disk_Num SMALLINT UNSIGNED NOT NULL, " \
    "4KiB INT UNSIGNED NOT NULL, " \
    "8KiB INT UNSIGNED NOT NULL, " \
    "16KiB INT UNSIGNED NOT NULL, " \
    "32KiB INT UNSIGNED NOT NULL, " \
    "64iB INT UNSIGNED NOT NULL, " \
    "128KiB INT UNSIGNED NOT NULL, " \
    "256KiB INT UNSIGNED NOT NULL, " \
    "512KiB INT UNSIGNED NOT NULL, " \
    "1MiB INT UNSIGNED NOT NULL, " \
    "2MiB INT UNSIGNED NOT NULL, " \
    "4MiB INT UNSIGNED NOT NULL, " \
    "Larger_Than_4MiB INT UNSIGNED NOT NULL, " \
    "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
    "INDEX( Hostname), INDEX( Disk_Num) )" \
    "ENGINE=HEAP" \
    ";"

# Note: We're hard-coding the size and latency buckets rather than trying to get
# them from the DDN API  (mainly because you can't have characters like <= in
# column names).  When SFAClient objects start up, they verify that the size
# buckets that the DDN controllers are using match what we expect.  If that
# ever changes, we'll obviously have to change this code, too.


class SFAMySqlDb(object):
    '''
    Encapsulates the database related tasks into one class with a fairly simple interface.
    '''


    def __init__(self, user, password, host, db_name, init = False ):
        '''
        Connect to the database and create the tables (if necessary)
        
        Note that we're deliberately *NOT* catching any exceptions that might
        be thrown.  There's really very little that this class could do to recover
        from any errors and without a database connection and properly initialized
        tables, this class is pretty useless.
        '''

        # Get the logger object
        self.logger = logging.getLogger( 'DDNTool_SFAMySqlDb')
        self.logger.debug( 'Creating instance of SFAMySqlDb')

        self._dbcon = mysql.connector.connect(user = user, password = password,
                                              host = host, database = db_name)
        if init:            
            self._create_schema()
        
 
    def update_lun_table( self, sfa_client_name, update_time, lun_num,
                          transfer_bw, read_bw, write_bw,
                          read_iops, write_iops, forwarded_bw, forwarded_iops,
                          pool_state):
        '''
        Updates the row in the lun info table for the specified 
        client and virtual disk.
        '''

        
        insert_query = "INSERT INTO " + TABLE_NAMES['LUN_TABLE_NAME'] +                 \
                "(Hostname, LastUpdate, Disk_Num, Transfer_BW, Read_BW, Write_BW, "     \
                "Read_IOPS, Write_IOPS, Forwarded_BW, Forwarded_IOPS, Pool_State) "     \
                "VALUES( %s, FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s) "   \
                "ON DUPLICATE KEY UPDATE LastUpdate=VALUES(LastUpdate), "               \
                "Transfer_BW=VALUES(Transfer_BW), Read_BW=VALUES(Read_BW), "            \
                "Write_BW=VALUES(Write_BW), Read_IOPS=VALUES(Read_IOPS), "              \
                "Write_IOPS=VALUES(Write_IOPS), Forwarded_BW=VALUES(Forwarded_BW), "    \
                "Forwarded_IOPS=VALUES(Forwarded_IOPS), Pool_State=VALUES(Pool_State);" 
        
        cursor = self._dbcon.cursor()
        cursor.execute( insert_query, (sfa_client_name, str(update_time),
                                       str(lun_num), str(transfer_bw),
                                       str(read_bw), str(write_bw),
                                       str(read_iops), str(write_iops),
                                       str(forwarded_bw), str(forwarded_iops),
                                       str(pool_state)))
        cursor.close()

    def update_raw_lun_table( self, sfa_client_name, update_time, lun_num,
                              transfer_bytes, read_bytes, write_bytes,
                              forwarded_bytes, total_ios, read_ios, write_ios,
                              forwarded_ios, pool_state):
        '''
        Updates the row in the raw lun info table for the specified 
        client and virtual disk.
        '''
        
        insert_query = "INSERT INTO " + TABLE_NAMES['RAW_LUN_TABLE_NAME'] +   \
                "(Hostname, LastUpdate, Disk_Num, Transfer_Bytes, "           \
                "Read_Bytes, Write_Bytes, Forwarded_bytes, "                  \
                "Total_IOs, Read_IOs, Write_IOs, Forwarded_IOs, Pool_State) " \
                "VALUES( %s, FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, " \
                "%s, %s, %s) "                                                \
                "ON DUPLICATE KEY UPDATE LastUpdate=VALUES(LastUpdate), "     \
                "Transfer_Bytes=VALUES(Transfer_Bytes), "                     \
                "Read_Bytes=VALUES(Read_Bytes), "                             \
                "Write_Bytes=VALUES(Write_Bytes), "                           \
                "Forwarded_Bytes=VALUES(Forwarded_Bytes), "                   \
                "Total_IOs=VALUES(Total_IOs), Read_IOs=VALUES(Read_IOs), "    \
                "Write_IOs=VALUES(Write_IOs), "                               \
                "Forwarded_IOs=VALUES(Forwarded_IOs), "                       \
                "Pool_State=VALUES(Pool_State);" 
        
        cursor = self._dbcon.cursor()
        cursor.execute( insert_query, (sfa_client_name, str(update_time),
                                        str(lun_num), str(transfer_bytes),
                                        str(read_bytes), str(write_bytes),
                                        str(forwarded_bytes),
                                        str(total_ios), str(read_ios),
                                        str(write_ios), str(forwarded_ios),
                                        str(pool_state)))
        cursor.close()
        
    def update_dd_table( self, sfa_client_name, update_time, dd_num,
                         transfer_bw, read_iops, write_iops):
        '''
        Updates the row in the disk table for the specified 
        client and virtual disk.
        '''

        replace_query = "REPLACE INTO " + TABLE_NAMES['DISK_TABLE_NAME'] + \
                        "(Hostname, LastUpdate, Disk_Num, Transfer_BW, "   \
                        "Read_IOPS, Write_IOPS) "                          \
                        "VALUES( %s, FROM_UNIXTIME(%s), %s, %s, %s, %s);"
     
        cursor = self._dbcon.cursor()
        cursor.execute( replace_query, (sfa_client_name, str(update_time),
                                        str(dd_num), str(transfer_bw),
                                        str(read_iops), str(write_iops)))
        cursor.close()

    def update_lun_request_size_table( self, sfa_client_name, update_time,
                                       lun_num, read_table, size_buckets):
        '''
        Update the read or write request size data (depending on the value of the read_table
        boolean) for one LUN on one client.  size_buckets is a list containing the
        number of requests for each size and is expected to match the size values listed in
        the column headings.
        '''
        
        replace_query = "REPLACE INTO "
        if read_table:
            replace_query += TABLE_NAMES["LUN_READ_REQUEST_SIZE_TABLE_NAME"]
        else:    
            replace_query += TABLE_NAMES["LUN_WRITE_REQUEST_SIZE_TABLE_NAME"]

        replace_query += " VALUES( %s, FROM_UNIXTIME(%s), %s" 
        
        for unused_i in range(len(size_buckets)):
            replace_query += ", %s"
        replace_query += ");"
       
        values = (sfa_client_name, str(update_time), str(lun_num))
        for size in size_buckets:
                values += (str(size), )
        # Note: it seems like I shouldn't have to convert all the sizes to strings manually,
        # but I get strange mysql errors if I don't...

        cursor = self._dbcon.cursor()
        cursor.execute( replace_query, values)
        cursor.close()

    def update_lun_request_latency_table( self, sfa_client_name, update_time,
                                          lun_num, read_table, latency_buckets):
        '''
        Update the read or write request latency data (depending on the value of the read_table
        boolean) for one lun on one client.  latency_buckets is a list containing
        the number of requests that were handled in each time frame and is expected to match
        the latency values listed in the column headings.
        '''

        replace_query = "REPLACE INTO "
        if read_table:
            replace_query += TABLE_NAMES["LUN_READ_REQUEST_LATENCY_TABLE_NAME"]
        else:
            replace_query += TABLE_NAMES["LUN_WRITE_REQUEST_LATENCY_TABLE_NAME"]

        replace_query += " VALUES( %s, FROM_UNIXTIME(%s), %s"

        for unused_i in range(len(latency_buckets)):
            replace_query += ", %s"
        replace_query += ");"

        values = (sfa_client_name, str(update_time), str(lun_num))
        for latency in latency_buckets:
                values += (str(latency), )
        # Note: it seems like I shouldn't have to convert all the values to strings manually,
        # but I get strange mysql errors if I don't...

        cursor = self._dbcon.cursor()
        cursor.execute( replace_query, values)
        cursor.close()

 
    def update_dd_request_size_table( self, sfa_client_name, update_time,
                                      disk_num, read_table, size_buckets):
        '''
        Update the read or write request size data (depending on the value of the read_table
        boolean) for one disk drive on one client.  size_buckets is a list containing the
        number of requests for each size and is expected to match the size values listed in
        the column headings.
        '''
        
        replace_query = "REPLACE INTO "
        if read_table:
            replace_query += TABLE_NAMES["DD_READ_REQUEST_SIZE_TABLE_NAME"]
        else:    
            replace_query += TABLE_NAMES["DD_WRITE_REQUEST_SIZE_TABLE_NAME"]
            
        replace_query += " VALUES( %s, FROM_UNIXTIME(%s), %s"
        
        for unused_i in range(len(size_buckets)):
            replace_query += ", %s"
        replace_query += ");"
        
        values = (sfa_client_name, str(update_time), str(disk_num))
        for size in size_buckets:
                values += (str(size), )
        # Note: it seems like I shouldn't have to convert all the sizes to strings manually,
        # but I get strange mysql errors if I don't...
        
        cursor = self._dbcon.cursor()
        cursor.execute( replace_query, values)
        cursor.close()
        
    def update_dd_request_latency_table( self, sfa_client_name, update_time,
                                         disk_num, read_table, latency_buckets):
        '''
        Update the read or write request latency data (depending on the value of the read_table
        boolean) for one disk drive on one client.  latency_buckets is a list containing
        the number of requests that were handled in each time frame and is expected to match
        the latency values listed in the column headings.
        '''

        replace_query = "REPLACE INTO "
        if read_table:
            replace_query += TABLE_NAMES["DD_READ_REQUEST_LATENCY_TABLE_NAME"]
        else:
            replace_query += TABLE_NAMES["DD_WRITE_REQUEST_LATENCY_TABLE_NAME"]
            
        replace_query += " VALUES( %s, FROM_UNIXTIME(%s), %s"
        
        for unused_i in range(len(latency_buckets)):
            replace_query += ", %s"
        replace_query += ");"
        
        values = (sfa_client_name, str(update_time), str(disk_num))
        for latency in latency_buckets:
                values += (str(latency), )
        # Note: it seems like I shouldn't have to convert all the values to strings manually,
        # but I get strange mysql errors if I don't...
        
        cursor = self._dbcon.cursor()
        cursor.execute( replace_query, values)
        cursor.close()


    def _create_schema(self):
        # Drop the old tables (since we're not storing long-term data, it's easier
        # to drop the old tables and re-create them than it is to use ALTER TABLE
        # statements.
        cursor = self._dbcon.cursor()
        cursor.execute( "SHOW TABLES;")
        results = cursor.fetchall()
        # results is a list of tuples - each tuple is one row.
        # In this case, there's only one value in each tuple: a table name
        cursor.close()

        values = TABLE_NAMES.values()         
        for result in results:
            if result[0] in values:
                cursor = self._dbcon.cursor()
                query = "DROP TABLE %s;"%result[0]
                cursor.execute( query)
                cursor.close()
        
        # create the new table(s)
        self._new_lun_table()
        self._new_raw_lun_table()
        self._new_dd_table()
        self._new_dd_read_request_size_table()
        self._new_dd_read_request_latency_table()
        self._new_dd_write_request_size_table()
        self._new_dd_write_request_latency_table() 
        self._new_lun_read_request_size_table()
        self._new_lun_read_request_latency_table()
        self._new_lun_write_request_size_table()
        self._new_lun_write_request_latency_table()

    def _query_exec(self, query):
        '''
        A quick helper function that exists because we kept repeating the same
        three lines of code in all the table create functions.
        '''

        cursor = self._dbcon.cursor()
        cursor.execute( query)
        cursor.close()

    def _new_lun_table(self):
        '''
        Create the db table that holds processed statistics on all the luns
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["LUN_TABLE_NAME"] + " "  \
        "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
        "Disk_Num SMALLINT UNSIGNED NOT NULL, "  \
        "Transfer_BW FLOAT, Read_BW FLOAT, Write_BW FLOAT, " \
        "READ_IOPS FLOAT, WRITE_IOPS FLOAT, "  \
        "Forwarded_BW FLOAT, FORWARDED_IOPS FLOAT, " \
        "Pool_State INT, " \
        "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
        "INDEX( Hostname), INDEX( Disk_Num) )"  \
        "ENGINE=HEAP" \
        ";"

        self._query_exec( table_def)
        
    def _new_raw_lun_table(self):
        '''
        Create the db table that holds raw statistics on all the luns
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["RAW_LUN_TABLE_NAME"] + " "  \
        "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
        "Disk_Num SMALLINT UNSIGNED NOT NULL, "  \
        "Transfer_Bytes BIGINT UNSIGNED, " \
        "Read_Bytes BIGINT UNSIGNED, Write_Bytes BIGINT UNSIGNED, " \
        "Forwarded_Bytes BIGINT UNSIGNED, " \
        "Total_IOs BIGINT UNSIGNED, "  \
        "Read_IOs BIGINT UNSIGNED, Write_IOs BIGINT UNSIGNED, "  \
        "Forwarded_IOs BIGINT UNSIGNED, "  \
        "Pool_State INT, " \
        "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
        "INDEX( Hostname), INDEX( Disk_Num) )"  \
        "ENGINE=HEAP" \
        ";"

        self._query_exec( table_def)

    def _new_dd_table(self):
        '''
        Create the db table that holds statistics on all the virtual disks
        '''
 
        # Note: this table is almost exactly the same as the virtual disk table.
        # Seems like we should be able to combine these 2 functions.
        table_def = \
        "CREATE TABLE " + TABLE_NAMES["DISK_TABLE_NAME"] + " "  \
        "(Hostname VARCHAR(75) NOT NULL, LastUpdate TIMESTAMP, " \
        "Disk_Num SMALLINT UNSIGNED NOT NULL, "  \
        "Transfer_BW FLOAT, READ_IOPS FLOAT, WRITE_IOPS FLOAT, "  \
        "CONSTRAINT unique_disk UNIQUE (Hostname, Disk_Num), "  \
        "INDEX( Hostname), INDEX( Disk_Num) )"  \
        "ENGINE=HEAP" \
        ";"

        self._query_exec( table_def)

# Virtual disk request size and latency tables
    def _new_lun_read_request_size_table( self):
        '''
        Create the db table that holds virtual disk read request size information.
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["LUN_READ_REQUEST_SIZE_TABLE_NAME"] + \
        " " + PARTIAL_SIZE_TABLE_DEF
        table_def = table_def.replace( 'Disk_Num', 'LUN')

        self._query_exec( table_def)

    def _new_lun_write_request_size_table( self):
        '''
        Create the db table that holds virtual disk write request size information.
        '''
        
        table_def = \
        "CREATE TABLE " + TABLE_NAMES["LUN_WRITE_REQUEST_SIZE_TABLE_NAME"] + \
        " " + PARTIAL_SIZE_TABLE_DEF
        table_def = table_def.replace( 'Disk_Num', 'LUN')

        self._query_exec( table_def)

    def _new_lun_read_request_latency_table( self):
        '''
        Create the db table that holds virtual disk read request latency information.
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["LUN_READ_REQUEST_LATENCY_TABLE_NAME"] + \
        " "  + PARTIAL_LUN_LATENCY_TABLE_DEF
        table_def = table_def.replace( 'Disk_Num', 'LUN')

        self._query_exec( table_def)

    def _new_lun_write_request_latency_table( self):
        '''
        Create the db table that holds virtual disk write request latency information.
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["LUN_WRITE_REQUEST_LATENCY_TABLE_NAME"] + \
        " "  + PARTIAL_LUN_LATENCY_TABLE_DEF
        table_def = table_def.replace( 'Disk_Num', 'LUN')

        self._query_exec( table_def)

# Disk drive request size and latency tables
    def _new_dd_read_request_size_table( self):
        '''
        Create the db table that holds disk drive read request size information.
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["DD_READ_REQUEST_SIZE_TABLE_NAME"] + \
        " " + PARTIAL_SIZE_TABLE_DEF

        self._query_exec( table_def)

    def _new_dd_write_request_size_table( self):
        '''
        Create the db table that holds disk drive write request size information.
        '''

        table_def = \
        "CREATE TABLE " + TABLE_NAMES["DD_WRITE_REQUEST_SIZE_TABLE_NAME"] + \
        " " + PARTIAL_SIZE_TABLE_DEF

        self._query_exec( table_def)

    def _new_dd_read_request_latency_table( self):
        '''
        Create the db table that holds disk drive read request latency information.
        '''
        
        table_def = \
        "CREATE TABLE " + TABLE_NAMES["DD_READ_REQUEST_LATENCY_TABLE_NAME"] + \
        " "  + PARTIAL_DD_LATENCY_TABLE_DEF
        
        self._query_exec( table_def)
    
    def _new_dd_write_request_latency_table( self):
        '''
        Create the db table that holds disk drive write request latency information.
        '''
        
        table_def = \
        "CREATE TABLE " + TABLE_NAMES["DD_WRITE_REQUEST_LATENCY_TABLE_NAME"] + \
        " "  + PARTIAL_DD_LATENCY_TABLE_DEF
        
        self._query_exec( table_def)



