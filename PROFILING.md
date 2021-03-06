# Profiling

To profile the encoding and decoding code use Aman Gupta's perftools.rb (https://github.com/tmm1/perftools.rb). It's really easy to use once you've set it up, and it generates graphs that make it pretty obvious where the  hotspots are.

## Setup

Start by installing perftools.rb:

    gem install perftools.rb

I have it installed in my global gemset, which is handy since you can profile projects that uses any other gemset without having to add perftools.rb to its Gemfile:

    rvm gemset use global
    gem install perftools.rb

If you look at the README for perftools.rb the way to use it seems really icky, having to set environment variables and all that. I have the following script saved as `~/bin/profile` to encapsulate all that:

    #!/bin/bash

    profile_id=$(date +'%Y%m%d%H%M%S')
    CPUPROFILE=/tmp/$profile_id RUBYOPT="-r`gem which perftools | tail -1`" $@
    pprof.rb --pdf /tmp/$profile_id > /tmp/$profile_id.pdf
    open /tmp/$profile_id.pdf

With this script you can prefix any command with "profile" and perftools.rb will be enabed, and a nice graph will be opened in Preview as soon as the program exits. This only works on OS X, obviously, but I'm sure it can be made to work on Linux too.

## How to profile the code

Most of the time you want to profile a specific method or piece of code. The easiest thing to do is write a short script that runs that code over and over again. This will make sure that the profile graph isn't swamped by noise from other parts of the code, and running lots of iterations means that the numbers will be more stable. Perhaps most importantly it will also show the impact of the GC.

    100000.times do
      strs.each do |str|
        AMQ::Client::Framing::String::Frame.decode(str)
      end
    end

In the code above the `strs` variable holds a list of strings I've stolen from the amqp-benchmarks repository. I call the `decode` method of the `AMQ::Client::Framing::String::Frame` class over and over again and after 100K iterations (this takes around ten seconds to run) I get a graph that shows me which parts of the code take most time.

This is how you run the script above (assuming you fill in the `strs` list and add the necessary require's -- and that you've followed the instructions at the top of this document -- and that you've named it "benchmark_script.rb"):

    profile ruby benchmark_script.rb

It will run for a few seconds and then open a graph. Next I'll explain how to interpret that graph.

## Interpreting the profile graph

The graph generated by perftools.rb shows all the methods that have run, which methods they call, how much time was spent in each method, and a lot of other very interesting things. 

At the top left of the picture it says mow many samples were taken. perftools.rb samples 100 times per second, so 1257 samples means that it ran for 12.57 seconds. The number of samples per second can be tweaked, but I've never had any reason to. The next three numbers just tell you that there are methods that were called not very often, and that these are not shown in the graph, to make it easier to read.

There are usually two, and sometimes three, nodes which don't have any arrows pointing into them. The first is the entry point into your application, the second the GC, and sometimes there is a third which usually is RubyGems or Bundler. There is no reason there can't be more top level nodes, but those are the ones I've seen.

Each node represents a method. The label is the class and method name, in classic Ruby style: ClassName#instance_method_name. Unfortunately it doesn't handle class methods very well, so all end up ass Class#method_name. This is bad for us, since most methods in amq-protocol are class methods. It also means that all class methods of the same name, regardless of which class then belong are represented as one node. That's really bad for us, since a lot of methods that we want to profile are called "decode" and "encode".

The numbers below the label are the self time and cumulative time measurements, first as samples and then, in parentheses as percentages of the whole. Self time means the time spent in the method, excluding other methods, and cumulative time means the total time spent in the method, and all methods below it in the call stack. In other words, if method a calls b and c, the cumulative time for a is its self time, plus the cumulative time of b and c (which is the self time of each of those, plus the cumulative time of the methods they call, and so on). 

The number by the arrow from one node to another is the number of samples that saw the source node call the destination node. Looking at the numbers by the arrows into a node you can see roughly which method calls the method represented by that node the most.

That's more or less it. I find the percentages most useful to work with, as the number of samples can vary a bit from time to time, its basically the same problem as using `time` to benchmark. Percentages are often much more stable.

In the next section I'll explain how to act on the information that the graph gives.

## Optimizing

The first thing to look at is the GC node. It will always be high (this is Ruby after all), but if it's above 20% this is what you should start with. The reason the GC takes so much time is because the code creates too many objects. It's not always obvious what is creating so many objects, but read the next section for how to remove the worst offenders. When you've picked the low hanging fruit and still have a high GC percentage, go over your code and try to see if there are places where you can memoize, cache, etc. If your objects are immutable you should never have to create two identical objects (on the other hand, it's easy to leak memory if you cache too much).

The next thing to look at is the node with the highest self time percentage. This is your first hotspot. Apply all the tricks in the next section and see if it makes any difference. Sometimes hotspots are hotspots because of design rather than slow code. If a method is called many, many times you may not be able to optimize it further (but try, each tiny thing will make a huge difference).

The third thing to look for are methods will high cumulative time. If the methods they call don't look too bad and can be optimized first, you may be able to rewrite the method to call them fewer times by caching values, for example.

While optimizing run the profiler for each change to make sure you're going in the right direction. It's not uncommon for something that you think should be faster to be slower because of something you couldn't foresee or some unexpected side effect. When the method you're working on is no longer the worst offender, move on to the next, and iterate.

## Tips

These are some general tips I've gathered while optimizing Ruby code:

* Avoid string literals. In contrast to Java, strings in Ruby are mutable, so each literal string is a separate object (otherwise 'a'.upcase! would have very strange side effects). Move string literals to constants.
* Avoid range literals. Just as with strings, ranges are objects and they are created every time they are encountered. Ranges are most often used to extract parts of a string, like `str[1..5]`. This can always be rewritten as a slice instead: `str[1, 4]` (the second argument is a length, not an index, so make sure you get the right value). Code like `data[offset..(offset + 4)]` is especially wasteful since it would be much clearer with the slice syntax: `data[offset, 5]`.
* Avoid regular expressions. They are convenient, but for code that will be called thousands of times you need to rewrite them using String#index and String#slice/[]. Make sure that your rewrite doesn't create a lot of temporary string objects.
* When reading files don't read line by line, and absolutely never byte by byte. It's much faster to read a big chunk (as in megabytes) and use String#split to split into lines. The same goes for writing. Buffer the lines and write them in one big chunk. Avoid IO#tell and #seek unless you're trying to read a few bytes out of a gigabyte file.
* Never ever, ever, use Date or DateTime, or require 'date' (to get Time.parse, for example). Date is so slow that it's not even funny. If you use Date.parse you can be sure that whatever else you do that method will account for at least half of the running time. If you really, really need date parsing and date perform date calculations, use the home_run gem, but for almost everything you can use the basic methods on Time (but those aren't cheap either).