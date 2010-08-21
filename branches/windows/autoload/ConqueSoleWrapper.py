""" {{{

ConqueSoleSubprocessWrapper

Subprocess wrapper to deal with Windows insanity. Launches console based python, 
which in turn launches originally requested command. Communicates with cosole
python through shared memory objects.

}}} """

import md5, time, pickle
import win32api, win32con, win32process

from ConqueSoleSharedMemory import * # DEBUG

import logging # DEBUG
LOG_FILENAME = 'pylog.log' # DEBUG
#logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG) # DEBUG

class ConqueSoleWrapper():

    # class properties {{{

    shm_key = ''

    # process info
    handle = None
    pid = None

    # queue input in this bucket
    bucket = ''

    # console size
    # NOTE: columns should never change after open() is called
    lines = 24
    columns = 80

    # line offset, since real console has limited scrollback
    line_offset = 0

    # shared memory objects
    shm_input   = None
    shm_output  = None
    shm_attributes = None
    shm_stats   = None
    shm_command = None
    shm_rescroll = None

    # console python process
    proc = None

    # path to python exe
    python_exe = 'C:\Python27\python.exe'

    # path to communicator
    communicator_py = 'conque_sole_communicator.py'

    # }}}

    #########################################################################
    # unused

    def __init__(self): # {{{
        pass

        # }}}

    #########################################################################
    # run communicator process which will in turn run cmd

    def open(self, cmd, options = {}): # {{{

        self.lines = options['LINES']
        self.columns = options['COLUMNS']

        # create a shm key
        self.shm_key = md5.new(cmd + str(time.ctime())).hexdigest()[:8]

        # python command
        cmd_line = '%s "%s" %s %d %d %s' % (self.python_exe, self.communicator_py, self.shm_key, int(self.columns), int(self.lines), cmd)
        logging.debug('python command: ' + cmd_line)

        # console window attributes
        flags = win32process.NORMAL_PRIORITY_CLASS | win32process.DETACHED_PROCESS
        si = win32process.STARTUPINFO()

        # start the stupid process already
        try:
            tpl_result = win32process.CreateProcess (None, cmd_line, None, None, 0, flags, None, '.', si)
        except:
            logging.debug('COULD NOT START %s' % cmd_line)
            raise

        # handle
        self.handle = tpl_result [0]
        self.pid = tpl_result [2]

        logging.debug('communicator pid: ' + str(self.pid))

        # init shared memory objects
        self.init_shared_memory(self.shm_key)

        # }}}

    #########################################################################
    # read output from shared memory

    def read(self, start_line, num_lines, timeout = 0): # {{{

        # emulate timeout by sleeping timeout time
        if timeout > 0:
            read_timeout = float(timeout) / 1000
            #logging.debug("sleep " + str(read_timeout) + " seconds")
            time.sleep(read_timeout)

        # factor in line offset to start position
        real_start = start_line - self.line_offset

        output = []
        attributes = []

        # get output
        for i in range(real_start, real_start + num_lines + 1):
            output.append(self.shm_output.read(self.columns, i * self.columns))
            attributes.append(self.shm_attributes.read(self.columns, i * self.columns))

        return (output, attributes)

        # }}}

    #########################################################################
    # get current cursor/scroll position

    def get_stats(self): # {{{

        try:
            rescroll_str = self.shm_rescroll.read()
            if rescroll_str != '' and rescroll_str != None:
                logging.debug('cmd found')
                rescroll = pickle.loads(rescroll_str)
                logging.debug(str(rescroll))

                self.shm_rescroll.clear()

                # close down old memory
                self.shm_output.close()
                self.shm_output = None

                self.shm_attributes.close()
                self.shm_attributes = None

                # reallocate memory
                logging.debug('new output size: ' + str(CONQUE_SOLE_BUFFER_LENGTH * self.columns * rescroll['data']['blocks']) + ' = ' + rescroll['data']['mem_key'])
                self.shm_output = ConqueSoleSharedMemory(CONQUE_SOLE_BUFFER_LENGTH * self.columns * rescroll['data']['blocks'], 'output', rescroll['data']['mem_key'], True)
                self.shm_output.create('write')

                self.shm_attributes= ConqueSoleSharedMemory(CONQUE_SOLE_BUFFER_LENGTH * self.columns * rescroll['data']['blocks'], 'attributes', rescroll['data']['mem_key'], True)
                self.shm_attributes.create('write')

            stats_str = self.shm_stats.read()
            if stats_str != '':
                self.stats = pickle.loads(stats_str)
            else:
                return False
        except Exception, e:
            logging.debug('Error closing pid: %s' % e)
            return False

        # add our own offset so it comes out the full scrollback position
        self.stats['top_offset'] += self.line_offset

        return self.stats

        # }}}

    #########################################################################
    # write input to shared memory

    def write(self, text): # {{{

        self.bucket += text

        logging.debug('bucket is ' + self.bucket)

        istr = self.shm_input.read()

        if istr == '':
            logging.debug('input shm is empty, writing')
            self.shm_input.write(self.bucket[:500])
            self.bucket = self.bucket[500:]

        # }}}

    #########################################################################
    # write virtual key code to shared memory using proprietary escape seq

    def write_vk(self, vk_code): # {{{

        seq = ur"\u001b[" + str(vk_code) + "VK"
        self.write(seq)

        # }}}

    #########################################################################
    # shut it all down

    def close(self): # {{{
        self.shm_command.write(pickle.dumps({'cmd' : 'close', 'data' : {} }))
        time.sleep(0.2)

        # }}}

    #########################################################################
    # create shared memory instance

    def window_resize(self, lines, columns): # {{{
        pass

        # }}}

    # ****************************************************************************
    # create shared memory objects
   
    def init_shared_memory(self, mem_key): # {{{

        self.shm_input = ConqueSoleSharedMemory(CONQUE_SOLE_INPUT_SIZE, 'input', mem_key)
        self.shm_input.create('write')
        self.shm_input.clear()

        self.shm_output = ConqueSoleSharedMemory(CONQUE_SOLE_BUFFER_LENGTH * self.columns, 'output', mem_key, True)
        self.shm_output.create('write')
        self.shm_output.clear()

        self.shm_attributes = ConqueSoleSharedMemory(CONQUE_SOLE_BUFFER_LENGTH * self.columns, 'attributes', mem_key, True)
        self.shm_attributes.create('write')
        self.shm_attributes.clear()

        self.shm_stats = ConqueSoleSharedMemory(CONQUE_SOLE_STATS_SIZE, 'stats', mem_key)
        self.shm_stats.create('write')
        self.shm_stats.clear()

        self.shm_command = ConqueSoleSharedMemory(CONQUE_SOLE_COMMANDS_SIZE, 'command', mem_key)
        self.shm_command.create('write')
        self.shm_command.clear()

        self.shm_rescroll = ConqueSoleSharedMemory(CONQUE_SOLE_RESCROLL_SIZE, 'rescroll', mem_key)
        self.shm_rescroll.create('write')
        self.shm_rescroll.clear()

        return True

        # }}}
