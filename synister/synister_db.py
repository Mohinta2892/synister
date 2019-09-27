from pymongo import MongoClient, IndexModel, ASCENDING
from configparser import ConfigParser
from copy import deepcopy
import logging

logger = logging.getLogger(__name__)


class SynisterDB(object):
    def __init__(self, credentials):
        with open(credentials) as fp:
            config = ConfigParser()
            config.readfp(fp)
            self.credentials = {}
            self.credentials["user"] = config.get("Credentials", "user")
            self.credentials["password"] = config.get("Credentials", "password")
            self.credentials["host"] = config.get("Credentials", "host")
            self.credentials["port"] = config.get("Credentials", "port")

        self.auth_string = 'mongodb://{}:{}@{}:{}'.format(self.credentials["user"],
                                                          self.credentials["password"],
                                                          self.credentials["host"],
                                                          self.credentials["port"])


        self.collections = ["synapses", "neurons", "supers"]


        self.synapse = {"x": None,
                        "y": None,
                        "z": None,
                        "synapse_id": None,
                        "skeleton_id": None,
                        "source_id": None}

        self.neuron = {"skeleton_id": None,
                       "super_id": None,
                       "nt_known": None}

        self.super = {"super_id": None,
                      "nt_guess": None}


    def get_synapse_by_position(self, db_name, x, y, z):
        db = self.__get_db(db_name)
        synapses = db["synapses"]

        matching_synapses = synapses.find({"$and": [{"z": round(z)},{"y": round(y)}, {"x": round(x)}]})
        synapse_documents = []
        for synapse in matching_synapses:
            synapse_documents.append(synapse)

        return synapse_documents

    def get_collection(self, db_name, collection_name):
        db = self.__get_db(db_name)
        collection = db[collection_name]

        collection_iterator = collection.find({})
        collection_documents = [c for c in collection_iterator]
        return collection_documents

    def get_neurotransmitters(self, db_name):
        neurons = self.get_collection(db_name, "neurons")
        supers = self.get_collection(db_name, "supers")

        nt_known = set([nt for n in neurons for nt in n["nt_known"]])
        nt_guess = set([nt for s in supers for nt in s["nt_guess"]])

        return nt_known, nt_guess


    def create(self, db_name, overwrite=False):
        logger.info("Create new synister db {}".format(db_name))
        db = self.__get_db(db_name)

        if overwrite:
            for collection in self.collections:
                logger.info("Overwrite {}.{}...".format(db_name, collection))
                db.drop_collection(collection)

        # Synapses
        synapses = db["synapses"]
        logger.info("Generate indices...")
        synapses.create_index([("z", ASCENDING), ("y", ASCENDING), ("x", ASCENDING)],
                                name="pos",
                                sparse=True)

        synapses.create_index([("synapse_id", ASCENDING)],
                           name="synapse_id",
                           sparse=True)

        synapses.create_index([("skeleton_id", ASCENDING)],
                               name="skeleton_id",
                               sparse=True)


        # Neurons
        neurons = db["neurons"]
        logger.info("Generate indices...")

        neurons.create_index([("skeleton_id", ASCENDING)],
                               name="skeleton_id",
                               sparse=True)

        # Supers
        supers = db["supers"]

    def add_synapse(self, db_name, x, y, z, synapse_id, skeleton_id,
                    nt_known, source_id, nt_guess=None, super_id=None):
        """
        Add a new synapse to the database. This entails generating 
        or adding a synapse, a neuron and optionally a super
        that specificies neurotransmitter guesses. The id 
        of the super should correspond to its identity. 
        Super ids are case insensitive. Existing supers 
        or neurons cannot be modified or overwritten with this 
        method, i.e. supers and neuron transmitter ids 
        have to be consistent before adding a new
        synapse.
        """

        if not isinstance(synapse_id, int):
            raise ValueError("Synapse id must be an integer type")
        if not isinstance(skeleton_id, int):
            raise ValueError("Skeleton id must be an integer type")

        if super_id is not None:
            if not isinstance(super_id, str):
                raise ValueError("Super id must be string or None type")

            super_id = super_id.upper()

        if not isinstance(source_id, str):
            raise ValueError("Source id must be a string")

        source_id = source_id.upper()

        if not isinstance(x, int):
            raise ValueError("x must be integer")
        if not isinstance(y, int):
            raise ValueError("y must be integer")
        if not isinstance(z, int):
            raise ValueError("z must be integer")
        if not isinstance(db_name, str):
            raise ValueError("db_name must be str")

        logger.info("Add synapse in DB {}".format(db_name))

        db = self.__get_db(db_name)

        synapses_to_insert = []
        neurons_to_insert = []
        supers_to_insert = []

        logger.info("Update synapses...")
        synapses = db["synapses"]
        synapse_entry = self.__generate_synapse(x, y, z, 
                                               synapse_id, 
                                               skeleton_id,
                                               source_id)

        synapse_in_db = synapses.find({"synapse_id": synapse_entry["synapse_id"]})
        assert(synapse_in_db.count()<=1)

        if synapse_in_db.count() == 1:
            for doc in synapse_in_db:
                x_known_in_db = doc["x"]
                y_known_in_db = doc["y"]
                z_known_in_db = doc["z"]
                skeleton_id_in_db = doc["skeleton_id"]
                source_id_in_db = doc["source_id"]

                x_to_add = synapse_entry["x"]
                y_to_add = synapse_entry["y"]
                z_to_add = synapse_entry["z"]
                skeleton_id_to_add = synapse_entry["skeleton_id"]
                source_id_to_add = synapse_entry["source_id"]

                if x_known_in_db != x_to_add:
                    raise ValueError("Synapse {} already in db but new x position does not match".format(synapse_id))
                if y_known_in_db != y_to_add:
                    raise ValueError("Synapse {} already in db but new y position does not match".format(synapse_id))
                if z_known_in_db != z_to_add:
                    raise ValueError("Synapse {} already in db but new z position does not match".format(synapse_id))
                if skeleton_id_in_db != skeleton_id_to_add:
                    raise ValueError("synapse {} already in db but assigned to a different skeleton".format(synapse_id))

        else: # count == 0
            synapses.insert_one(synapse_entry)

        logger.info("Update neurons...")
        neurons = db["neurons"]
        neuron_entry = self.__generate_neuron(skeleton_id, super_id, nt_known)

        neuron_in_db = neurons.find({"skeleton_id": neuron_entry["skeleton_id"]})
        assert(neuron_in_db.count()<=1)
        
        if neuron_in_db.count() == 1:
            for doc in neuron_in_db:
                nt_known_in_db = set(doc["nt_known"])
                super_id_in_db = doc["super_id"]

                nt_known_to_add = set(neuron_entry["nt_known"])
                super_id_to_add = neuron_entry["super_id"][0]
                
                if nt_known_in_db != nt_known_to_add:
                    raise ValueError("neuron {} already in db but has different known neurotransmitters".format(skeleton_id))

                if super_id_in_db != super_id_to_add:
                    raise ValueError("neuron {} already in db but assigned to a different super".format(skeleton_id))

        else: # count == 0
            neurons.insert_one(neuron_entry)

        logger.info("Update supers...")
        if super_id is None:
            assert(nt_guess is None)
        else:
            supers = db["supers"]
            super_entry = self.__generate_super(super_id, nt_guess)
            
            super_in_db = supers.find({"super_id": super_id})
            assert(super_in_db.count()<=1)

            if super_in_db.count() == 1:
                for doc in super_in_db:
                    nt_guess_in_db = set(doc["nt_guess"])
                    nt_guess_to_add = set(doc["nt_guess"])

                    if nt_guess_in_db != nt_guess_to_add:
                        raise ValueError("super {} already in db but has different neurotransmitter guess".format(super_id))
 

            else: # count == 0
                supers.insert_one(super_entry)

    def update_synapse(self, synapse_id, 
                       db_name, x=None, 
                       y=None, z=None,
                       skeleton_id=None, 
                       source_id=None):

        db = self.__get_db(db_name)
        synapses = db["synapses"]

        synapses.update_one({"synapse_id": synapse_id}, 
                {"$set": [{arg: locals()[arg]} for arg in\
                          ("x", "y", "z", "skeleton_id", "source_id")\
                          if not locals()[arg] is None]})

    def get_synapses_by_nt(self, 
                           db_name,
                           neurotransmitters):

        db = self.__get_db(db_name)
        synapses = db["synapses"]

        neurons = self.get_collection(db_name, "neurons")
        synapses = self.get_collection(db_name, "synapses")

        nt_to_synapses = {tuple(nt): [] for nt in neurotransmitters}
        for nt in neurotransmitters:
            neurons_with_nt = [neuron for neuron in neurons if set(neuron["nt_known"])==set(nt)]
            if not neurons_with_nt:
                raise ValueError("No neuron with nt {} in database {}".format(nt, database))

            for neuron in neurons_with_nt:
                synapses_with_nt = [synapse for synapse in synapses if synapse["skeleton_id"] == neuron["skeleton_id"]]
                nt_to_synapses[tuple(nt)].extend(synapses_with_nt)

        return nt_to_synapses


    def make_split(self,
                   db_name,
                   split_name,
                   train_synapse_ids,
                   test_synapse_ids):

        
        db = self.__get_db(db_name)
        synapses = db["synapses"]

        synapses.update_many({"synapse_id": {"$in": train_synapse_ids}},
                             {"$set": {split_name: "train"}})

        synapses.update_many({"synapse_id": {"$in": test_synapse_ids}},
                             {"$set": {split_name: "test"}})


    def read_split(self, 
                   db_name,
                   split_name):

        db = self.__get_db(db_name)
        synapses = self.get_collection(db_name, "synapses")

        train_synapses = []
        test_synapses = []
        for synapse in synapses:
            try:
                if synapse[split_name] == "train":
                    train_synapses.append(synapse)
                elif synapse[split_name] == "test":
                    test_synapses.append(synapse)
                else:
                    raise ValueError("Split {} corrupted, abort".format(split_name))
            except KeyError:
                pass

        return train_synapses, test_synapses


    def get_synapse_locations(self, db_name, split_name, split, neurotransmitter):
        if not split in ["train", "test"]:
            raise ValueError("Split must be either train or test")

        nts = self.get_neurotransmitters(self, db_name)
        if not neurotransmitter in nts:
            raise ValueError("{} not in database.".format(neurotransmitter))

        train_synapses, test_synapses = self.read_split(db_name, split_name)
       
        if split == "train":
            synapses = train_synapses
        else:
            synapses = test_synapses

        if not isinstance(neurotransmitter, list):
            neurotransmitter = list(neurotransmitter)
        locations = [[int(s["z"]), int(s["y"]), int(s["z"])] for s in synapses if set(s["nt_known"]) == set(neurotransmitter)]
        return locations


    def update_neuron(self, skeleton_id, 
                      db_name, super_id=None, 
                      nt_known=None):

        db = self.__get_db(db_name)
        neurons = db["neurons"]

        neurons.update_one({"skeleton_id": skeleton_id}, 
                {"$set": [{arg: locals()[arg]} for arg in\
                          ("super_id", "nt_known")\
                          if not locals()[arg] is None]})

    def update_super(self, super_id, 
                     db_name, nt_guess=None):

        db = self.__get_db(db_name)
        supers = db["supers"]

        supers.update_one({"skeleton_id": skeleton_id}, 
                {"$set": [{arg: locals()[arg]} for arg in\
                          ("nt_guess")\
                          if not locals()[arg] is None]})

    def __get_client(self):
        client = MongoClient(self.auth_string, connect=False)
        return client

    def __get_db(self, db_name):
        client = self.__get_client()
        db = client[db_name]
        return db 

    def __generate_synapse(self, x, y, z, synapse_id, skeleton_id, source_id):
        synapse = deepcopy(self.synapse)
        synapse["x"] = x
        synapse["y"] = y
        synapse["z"] = z
        synapse["synapse_id"] = synapse_id
        synapse["skeleton_id"] = skeleton_id
        synapse["source_id"] = str(source_id).upper()
        return synapse

    def __generate_neuron(self, skeleton_id, super_id, nt_known):
        neuron = deepcopy(self.neuron)
        neuron["skeleton_id"] = skeleton_id
        neuron["super_id"] = str(super_id).upper()
        if isinstance(nt_known, list):
            neuron["nt_known"] = [str(nt).lower() for nt in nt_known]
        else:
            neuron["nt_known"] = [str(nt_known).lower()]
        return neuron

    def __generate_super(self, super_id, nt_guess):
        """
        A super is a superset of neurons and thus
        includes, but is not limited to, hemilineages.
        """

        super_ = deepcopy(self.super)
        super_["super_id"] = str(super_id)
        if isinstance(nt_guess, list):
            super_["nt_guess"] = [str(nt).lower() for nt in nt_guess]
        else:
            super_["nt_guess"] = [str(nt_guess).lower()]

        return super_
