# -*- coding: utf-8 -*-

import pufsim
from math import exp
from numpy import around, sign, zeros
from scipy.spatial import distance
import sys
from copy import copy

class ArbiterLR():

    class triGen:

        prev = None
        cur = None
        nxt = None

        def __init__(self, default):
            self.default = default
            self.prev = copy(default)
            self.cur = copy(default)
            self.nxt = copy(default)

        def iterate(self):
            self.prev = self.cur
            self.cur = self.nxt
            self.nxt = copy(self.default)

    # return the (standard) scalar product of two vectors x and y
    def sprod(self, x, y):
        if len(x) != len(y):
            raise RuntimeError('Both arguments must be vectors of the same length.')
        return sum([ x[i]*y[i] for i in range(len(x)) ])

    # logistic function
    def h(self, x, Θ):
        p = -self.sprod(Θ, x)
        try:
            if p > 500:
                # avoid overflow
                return 0
            return 1.0 / (1 + exp(p))
        except OverflowError as e:
            sys.stdout.write("\nh: overflow for p=" + str(p) + "x=" + str(["%8f" % e for e in x]) + ", Θ=" + str(["%8f" % e for e in Θ]))
            raise e

    # compute input product
    def inputProd(self, c):
        return [
            (-1)**sum([c[j] for j in range(i,self.k)])
            for i in range(len(c))
        ]

    def __init__(self, k, m, M, n):
        # experiment parameters
        self.k = k # pf size
        self.m = min([2**k, m]) # training set size
        self.M = M # number of wrong CRPs
        self.n = min([2**k, n]) # check set size
        self.convergeDecimals = 8 # number of decimals expected to be equal after one iteration
        self.maxTrainingIteration = 100
        self.pf = self.generatePF()

    def generatePF(self):
        # create pufsim with k multiplexer instances
        return pufsim.puf(pufsim.RNDNormal(), self.k)

    def generateTrainingSet(self):
        # sample training set
        tChallenges = pufsim.genChallengeList(self.k, self.m + self.M)
        # add correct challenges
        tSet = [ (self.modChallengeForTraining([1] + self.inputProd(c)), self.pf.challengeBit(c)) for c in tChallenges[:self.m] ]
        # add wrong challenges
        tSet += [ (self.modChallengeForTraining([1] + self.inputProd(c)), 1-self.pf.challengeBit(c)) for c in tChallenges[self.m:] ]

        return tSet

    def modChallengeForTraining(self, c):
        return c

    def train(self, tDim=None):
        tSet = self.generateTrainingSet()

        if tDim is None:
            tDim = self.k+1

        converged = False
        i = 0

        # RPROP parameters
        ηplus = 1.2
        ηminus = 0.5
        Δmin = 10**-6
        Δmax = 50

        # learned delay values
        Θ = self.triGen([ 1 for x in range(tDim) ])

        # partial derivatives of error function
        pE = self.triGen(default=[ 0 for x in range(tDim) ])

        # update values for Θ
        Δ = self.triGen(default=[ 0 for x in range(tDim) ])
        Δ.cur = [ 1 for x in range(tDim) ] # init for first iteration
        ΔΘ = self.triGen(default=[ 0 for x in range(tDim) ])

        try:
            while (not converged and i < self.maxTrainingIteration):
                # count iterations
                i += 1

                # compute new Θ (RPROP algorithm)
                print()
                for j in range(tDim):
                    print("\rcomputing derivative: " + str(j) + "/" + str(tDim) + "                   ", end="", flush=True)

                    # compute pE.cur[j]
                    pE.cur[j] = 1/float(self.m+self.M) * sum([ tSet[i][0][j] * ( self.h(tSet[i][0], Θ.cur) - tSet[i][1] ) for i in range(self.m+self.M)])

                    # compute Θ.nxt[j]
                    if pE.prev[j]*pE.cur[j] > 0:
                        Δ.cur[j] = min([Δ.prev[j] * ηplus, Δmax])
                        ΔΘ.cur[j] = -sign(pE.cur[j]) * Δ.cur[j]
                        Θ.nxt[j] = Θ.cur[j] + ΔΘ.cur[j]

                    elif pE.prev[j]*pE.cur[j] < 0:
                        Δ.cur[j] = max([Δ.prev[j] * ηminus, Δmin])
                        Θ.nxt[j] = Θ.cur[j] - ΔΘ.prev[j]
                        pE.cur[j] = 0

                    elif pE.prev[j]*pE.cur[j] == 0:
                        ΔΘ.cur[j] = -sign(pE.cur[j]) * Δ.cur[j]
                        Θ.nxt[j] = Θ.cur[j] + ΔΘ.cur[j]

                print()

                # iterate the triGens Δ, ΔΘ, Θ, pE
                Δ.iterate()
                ΔΘ.iterate()
                Θ.iterate()
                pE.iterate()

                # check for convergence
                converged = (around(Θ.prev,decimals=self.convergeDecimals) == around(Θ.cur,decimals=self.convergeDecimals)).all()
                sys.stdout.write("Θ(" + str(i) + "): ") # + str(["%8f" % e for e in Θ.cur]) + "; ")
                sys.stdout.write(str(i) + "th iteration -- current distance: " + str(round(distance.euclidean(Θ.prev, Θ.cur), self.convergeDecimals+2)) + "\n")

        except OverflowError as e:
            #print()
            print("OVERFLOW OCCURED, USING LAST KNOWN Θ [" + str(e) + "]")
            Θ.cur = Θ.prev

        self.Θ = Θ.cur
        return self.Θ

    def check(self):
        # assess quality
        cChallenges = pufsim.genChallengeList(self.k, self.n)
        good = 0
        bad = 0
        for c in cChallenges:
            pfResponse = self.pf.challengeBit(c)
            lrResponse = 0 if self.sprod(self.Θ, self.modChallengeForTraining([1] + self.inputProd(c))) < 0 else 1
            if pfResponse == lrResponse:
                good += 1
            else:
                bad += 1
                #print("got " + str(lrResponse) + " but expected " + str(pfResponse))

        return float(good)/float(good+bad)

    def run(self):
        self.train()
        return self.check()


class ArbiterLRWithInterpolation(ArbiterLR):

    def generateTrainingSet(self):
        tSet = super(ArbiterLRWithInterpolation, self).generateTrainingSet()

        additionalTSet = []
        for crp in tSet:
            CRP1 = (copy(crp[0]), crp[1])
            CRP1[0][0] = CRP1[0][0] ^ 1

            CRP2 = (copy(crp[0]), crp[1] ^ 1)
            CRP2[0][self.k-1] = CRP2[0][self.k-1] ^ 1

            additionalTSet += [CRP1, CRP2]

        return tSet + additionalTSet

class CombinedArbiterLR(ArbiterLR):

    #def __init__(self, k, m, M, n):
    #    super(ArbiterLRWithInterpolation, self).__init__(k, m, M, n)

    def generatePF(self):
        # create pufsim with k multiplexer instances
        return pufsim.simpleCombiner(pufsim.RNDNormal(), self.k)

    def tensor(self, m, n):
        r = []
        for i in range(len(m)):
            for j in range(len(n)):
                r.append(m[i]*n[j])
        return r

    def modChallengeForTraining(self, c):
        c1 = copy(c)
        c2 = copy(c)
        c3 = copy(c)
        c4 = copy(c)
        t = self.tensor(self.tensor(self.tensor(c1, c2), c3), c4)
        return t

    def run(self):
        self.train((self.k+1)**4)
        return self.check()


debug = True

if debug:
    k = 8
    m = 15
    M = 0
    n = 10000
    l = 4 # currently hardcoded -- this variable unused

    lr = CombinedArbiterLR(k, m, M, n)
    print("DEBUG! k=%s,m=%s,M=%s,n=%s,l=%s," % (k,m,M,n,l), flush=True)
    print("\n\nRESULT " + str(lr.run()))

else:
    result = zeros((20, 11, 1))
    for iIdx in range(0, 1):
        for mIdx in range(0, 20):
            m = 100 * (mIdx+1)
            for MIdx in range(11):
                try:
                    M = int(m * (MIdx/10.0))
                    lr = CombinedArbiterLR(k=64, m=m, M=M, n=10000)
                    sys.stdout.write("%s,%s,%s,%s,%s," % (m,M,mIdx,MIdx,iIdx))
                    result[mIdx][MIdx][iIdx] = lr.run()
                    sys.stdout.write("%s\n" % result[mIdx][MIdx][iIdx])
                except Exception as e:
                    sys.stdout.write("%s\n" % str(e))

                #sys.stderr.write(str(result) + "\n\n###################\n\n")