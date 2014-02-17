"""
Specifications of Amazon instances. Taken from
http://aws.amazon.com/ec2/instance-types/instance-details/

Allows us to test the code in salty-dsd againsts all types of instances. It can
also help us (along with the application's integration tests) choose the most
appropriate instance type for our applications based on empirical evidence. It
also lets you use the stats for any other purpose.

TODO: Write a test to check in case the reference data changes
"""


class AWSInstanceSpec(object):
    """Encapsulate the spec of an instance """
    def __init__(self):
        """Some general defaults"""
        self.instance_family = "General Purpose"
        self.arch32 = False
        self.arch64 = True
        self.ebs_optimised = False
        self.first_ephemeral = '/dev/xvde2'
        self.price_units = "USD/hour"
        self.price_updated = "14/10/2013"

    def get_instancetype(self):
        """Get the name to use with boto, aws etc."""
        return str(self.__class__.__name__).lower().replace('_', '.')

    def get_ephemeral_devicenames(self):
        """
        Determine the device names that the ephemeral storage will use, under
        the assumption that they will increment monotonically from the
        particular device that instance type uses.
        """
        count = len(self.ephemeral_storage)
        first = self.first_ephemeral

        if count == 0:
            return []
        if count == 1:
            return [first]
        if count > 1:
            lbase = first[:-1]
            lchar = first[-1]

            # Some manifest themselves as partitions
            try:
                lchar = int(lchar)
                devicenames = [first]
                for i in range(1, count):
                    devicenames.append("{0}{1}".format(lbase, lchar + i))
                return devicenames

            # Others manifest themselves as disks
            except ValueError:
                devicenames = [first]
                for i in range(1, count):
                    devicenames.append("{0}{1}".format(lbase,
                                                       chr(ord(lchar) + i)))
                return devicenames

    def get_ebs_devicenames(self, volume_ids):
        """
        Determine the mount points that EBS storage may use for the particular
        instance type.
        """
        d = []
        for volume_id, i in enumerate(volume_ids):
            device = "/dev/sd%s" % chr(102 + i)
            d.append((device, volume_id))
        return d

    def __repr__(self):
        """Pretty print the class name"""
        return str(self.__class__.__name__)


class M1_Small(AWSInstanceSpec):
    """
    M1 Small.
    """
    def __init__(self):
        super(M1_Small, self).__init__()
        self.arch32 = True
        self.ephemeral_storage = [160]
        self.vcpu = 1
        self.ecu = 1
        self.mem = 1.7
        self.net = "L"
        self.price = 0.06


class M1_Medium(AWSInstanceSpec):
    """
    M1 Medium.
    """
    def __init__(self):
        super(M1_Medium, self).__init__()
        self.arch32 = True
        self.ephemeral_storage = [410]
        self.vcpu = 1
        self.ecu = 2
        self.mem = 3.75
        self.net = "M"
        self.first_ephemeral = "/dev/xvdf"
        self.price = 0.12


class M1_Large(AWSInstanceSpec):
    """
    M1 Large.
    """
    def __init__(self):
        super(M1_Large, self).__init__()
        self.ephemeral_storage = [420] * 2
        self.ebs_optimised = True
        self.vcpu = 2
        self.ecu = 4
        self.mem = 7.5
        self.net = "M"
        self.first_ephemeral = "/dev/xvdf"
        self.price = 0.24


class M1_XLarge(AWSInstanceSpec):
    """
    M1 X Large
    """
    def __init__(self):
        super(M1_XLarge, self).__init__()
        self.ephemeral_storage = [420] * 4
        self.ebs_optimised = True
        self.first_ephemeral = "/dev/xvdb"
        # Except it's not, we're overriding this with a blockdevie mapping
        self.first_ephemeral = "/dev/xvdf"
        self.vcpu = 4
        self.ecu = 8
        self.mem = 15
        self.net = "H"
        self.price = 0.48


class M3_XLarge(AWSInstanceSpec):
    """
    M3 X Large
    """
    def __init__(self):
        super(M3_XLarge, self).__init__()
        self.ephemeral_storage = []
        self.ebs_optimised = True
        self.vcpu = 4
        self.ecu = 13
        self.mem = 15
        self.net = "M"
        self.price = 0.50


class M3_2XLarge(AWSInstanceSpec):
    """
    M3 2 X Large
    """
    def __init__(self):
        super(M3_2XLarge, self).__init__()
        self.ephemeral_storage = []
        self.ebs_optimised = True
        self.vcpu = 8
        self.ecu = 26
        self.mem = 30
        self.net = "H"
        self.price = 1


class C1_Medium(AWSInstanceSpec):
    """
    C1 Medium
    """
    def __init__(self):
        super(C1_Medium, self).__init__()
        self.instance_family = "Compute optimised"
        self.arch32 = True
        self.ephemeral_storage = [350]
        self.vcpu = 2
        self.ecu = 5
        self.mem = 1.7
        self.net = "M"
        self.price = 0.145


class C1_XLarge(AWSInstanceSpec):
    """
    C1 X Large
    """
    def __init__(self):
        super(C1_XLarge, self).__init__()
        self.instance_family = "Compute optimised"
        self.ephemeral_storage = [420] * 4
        self.ebs = True
        self.vcpu = 8
        self.ecu = 20
        self.mem = 7
        self.net = "H"
        self.price = 0.58


# What happened to CC2_4XLarge?


class CC2_8XLarge(AWSInstanceSpec):
    """
    CC2 8 X Large
    """
    def __init__(self):
        super(CC2_8XLarge, self).__init__()
        self.instance_family = "Compute optimised"
        self.ephemeral_storage = [840] * 4
        self.vcpu = 32
        self.ecu = 88
        self.mem = 60.5
        self.net = "10G"
        self.price = 2.4


class M2_XLarge(AWSInstanceSpec):
    """
    M2 X Large
    """
    def __init__(self):
        super(M2_XLarge, self).__init__()
        self.instance_family = "Memory optimised"
        self.ephemeral_storage = [420]
        self.vcpu = 2
        self.ecu = 6.5
        self.mem = 17.1
        self.net = "M"
        self.price = 0.41


class M2_2XLarge(AWSInstanceSpec):
    """
    M2 2 X Large
    """
    def __init__(self):
        super(M2_2XLarge, self).__init__()
        self.instance_family = "Memory optimised"
        self.ephemeral_storage = [850]
        self.ebs_optimised = True
        self.vcpu = 4
        self.ecu = 13
        self.mem = 34.2
        self.net = "M"
        self.price = 0.82


class M2_4XLarge(AWSInstanceSpec):
    """
    M2 4X Large
    """
    def __init__(self):
        super(M2_4XLarge, self).__init__()
        self.instance_family = "Memory optimised"
        self.ephemeral_storage = [840] * 2
        self.ebs_optimised = True
        self.vcpu = 8
        self.ecu = 26
        self.mem = 68.4
        self.net = "H"
        self.price = 1.64


class CR1_8XLarge(AWSInstanceSpec):
    """
    CR1 8 X Large
    """
    def __init__(self):
        super(CR1_8XLarge, self).__init__()
        self.instance_family = "Memory optimised"
        self.ephemeral_storage = [120, 120]
        self.vcpu = 32
        self.ecu = 88
        self.mem = 244
        self.net = "10G"
        self.price = 3.5


class Hi1_4XLarge(AWSInstanceSpec):
    """
    Hi1 4 X Large
    """
    def __init__(self):
        super(Hi1_4XLarge).__init__()
        self.instance_family = "SSD 10 Gigabit4 Storage optimized"
        self.ephemeral_storage = [1024] * 2
        self.vcpu = 16
        self.ecu = 35
        self.mem = 60.5
        self.net = "10G"
        self.price = 3.1


class Hs1_8XLarge(AWSInstanceSpec):
    """
    HS1 8 X Large
    """
    def __init__(self):
        super(Hs1_8XLarge, self).__init__()
        self.instance_family = "SSD2 10 Gigabit4 Storage optimized"
        self.ephemeral_storage = [2048] * 2
        self.vcpu = 16
        self.ecu = 35
        self.mem = 117
        self.net = "10G"
        self.price = 4.6


class T1_Micro(AWSInstanceSpec):
    """
    T1 Micro
    """
    def __init__(self):
        super(T1_Micro, self).__init__()
        self.instance_family = "Micro instances"
        self.arch32 = True
        self.ephemeral_storage = []
        self.vcpu = 1
        self.ecu = 0.5
        self.mem = 1.7
        self.net = "L"
        self.price = 0.02


class Cg1_4XLarge(AWSInstanceSpec):
    """
    CG1 4 X Large
    """
    def __init__(self):
        super(Cgi1_4XLarge, self).__init__()
        self.instance_family = "GPU instances"
        self.ephemeral_storage = [2048] * 24
        self.vcpu = 16
        self.ecu = 33.5
        self.mem = 22.5
        self.net = "10G"
        self.price = 2.1


AWS_INSTANCE_SPECS = [
    M1_Small,
    M1_Medium,
    M1_Large,
    M1_XLarge,
    #M3_XLarge,
    #M3_2XLarge,
    C1_Medium,
    #C1_XLarge,
    #CC2_8XLarge,
    #M2_XLarge,
    #M2_2XLarge,
    #M2_4XLarge,
    #CR1_8XLarge,
    #Hi1_4XLarge,
    #Hs1_8XLarge,
    #T1_Micro,
    #Cg1_4XLarge
]


def get_aws_specs():
    """Prints AWS specs"""
    print("InstanceType | CPU | ECU | RAM  | NET | OptEBS | Price | Ephemerals")
    for AWSClass in AWS_INSTANCE_SPECS:
        spec = AWSClass()
        print "{0: <12} | {1: <3} |  {6}  | {2: <4} |   {3: <3} | {4: <6} | {7} | {5}".format(
            spec.__class__.__name__,
            spec.vcpu,
            spec.mem,
            spec.net,
            spec.ebs_optimised,
            spec.ephemeral_storage,
            spec.ecu,
            spec.price
        )
